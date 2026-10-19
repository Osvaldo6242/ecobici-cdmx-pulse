"""Station-level analytics: behavioural clustering, network centrality and rebalancing risk."""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

from . import config

# ---------------------------------------------------------------- clustering


def profile_matrix(profile: pd.DataFrame) -> pd.DataFrame:
    """48-dim working-day vector (24h departures + 24h arrivals), normalised per station."""
    wd = profile[~profile["is_non_working_day"]]
    dep = wd.pivot(index="station_code", columns="hour_of_day", values="avg_departures")
    arr = wd.pivot(index="station_code", columns="hour_of_day", values="avg_arrivals")
    m = pd.concat([dep.add_prefix("dep_"), arr.add_prefix("arr_")], axis=1).fillna(0)
    total = m.sum(axis=1)
    m = m[total >= 5]                                   # ignore near-inactive stations
    return m.div(m.sum(axis=1), axis=0)


def _name_cluster(c: pd.Series) -> str:
    am_dep = c[[f"dep_{h}" for h in range(6, 10)]].sum()
    am_arr = c[[f"arr_{h}" for h in range(6, 10)]].sum()
    pm_dep = c[[f"dep_{h}" for h in range(17, 21)]].sum()
    night = c[[f"dep_{h}" for h in (20, 21, 22, 23)]].sum() + c[[f"arr_{h}" for h in (20, 21, 22, 23)]].sum()
    if am_arr > 1.6 * am_dep and pm_dep > am_dep:
        return "Destino laboral"
    if am_dep > 1.6 * am_arr:
        return "Origen residencial"
    if night > 0.18:
        return "Vida nocturna y ocio"
    return "Uso mixto equilibrado"


def cluster_stations(profile: pd.DataFrame, k_range=range(3, 8)) -> dict:
    X = profile_matrix(profile)
    scores = {}
    for k in k_range:
        labels = KMeans(k, n_init=10, random_state=config.RANDOM_STATE).fit_predict(X)
        scores[k] = silhouette_score(X, labels)
    best_k = max(scores, key=scores.get)
    km = KMeans(best_k, n_init=20, random_state=config.RANDOM_STATE).fit(X)
    centroids = pd.DataFrame(km.cluster_centers_, columns=X.columns)

    names, seen = [], {}
    for _, c in centroids.iterrows():
        base = _name_cluster(c)
        seen[base] = seen.get(base, 0) + 1
        names.append(base if seen[base] == 1 else f"{base} {seen[base]}")

    coords = PCA(2, random_state=config.RANDOM_STATE).fit_transform(X)
    assign = pd.DataFrame({"station_code": X.index, "cluster": km.labels_,
                           "cluster_name": [names[i] for i in km.labels_],
                           "pca_x": coords[:, 0], "pca_y": coords[:, 1]})
    return {"assignments": assign, "centroids": centroids, "names": names,
            "silhouette": {int(k): float(v) for k, v in scores.items()}, "k": best_k}


# ---------------------------------------------------------------- network


def network(od: pd.DataFrame, min_trips: int = 20) -> dict:
    edges = od[(od["start_station"] != od["end_station"]) & (od["trips"] >= min_trips)]
    G = nx.DiGraph()
    G.add_weighted_edges_from(edges[["start_station", "end_station", "trips"]].itertuples(index=False))
    pagerank = nx.pagerank(G, weight="weight")
    U = G.to_undirected()
    for u, v in U.edges():
        U[u][v]["weight"] = G.get_edge_data(u, v, {}).get("weight", 0) + G.get_edge_data(v, u, {}).get("weight", 0)
    communities = nx.community.louvain_communities(U, weight="weight", seed=config.RANDOM_STATE, resolution=1.0)
    comm = {n: i for i, c in enumerate(sorted(communities, key=len, reverse=True)) for n in c}
    modularity = nx.community.modularity(U, communities, weight="weight")
    round_trip_share = od.loc[od["start_station"] == od["end_station"], "trips"].sum() / od["trips"].sum()
    return {
        "nodes": pd.DataFrame({"station_code": list(pagerank), "pagerank": list(pagerank.values()),
                               "community": [comm.get(n, -1) for n in pagerank]}),
        "n_communities": len(communities),
        "modularity": float(modularity),
        "edges": int(G.number_of_edges()),
        "round_trip_share": float(round_trip_share),
    }


# ---------------------------------------------------------------- rebalancing


def rebalancing_risk(reb: pd.DataFrame) -> pd.DataFrame:
    """Peak cumulative surplus/deficit relative to dock capacity on an average working day."""
    g = reb.groupby("station_code")
    out = pd.DataFrame({
        "max_surplus": g["cumulative_net"].max(),
        "max_deficit": g["cumulative_net"].min(),
        "capacity": g["capacity"].first(),
        "hour_of_peak_deficit": g.apply(lambda d: int(d.loc[d["cumulative_net"].idxmin(), "hour_of_day"]),
                                        include_groups=False),
        "hour_of_peak_surplus": g.apply(lambda d: int(d.loc[d["cumulative_net"].idxmax(), "hour_of_day"]),
                                        include_groups=False),
    }).reset_index()
    cap = out["capacity"].clip(lower=1)
    out["risk_empty"] = (-out["max_deficit"] / cap).clip(lower=0)
    out["risk_full"] = (out["max_surplus"] / cap).clip(lower=0)
    out["risk"] = out[["risk_empty", "risk_full"]].max(axis=1)
    out["risk_type"] = np.where(out["risk_empty"] >= out["risk_full"], "se vacía", "se llena")
    return out.sort_values("risk", ascending=False).reset_index(drop=True)
