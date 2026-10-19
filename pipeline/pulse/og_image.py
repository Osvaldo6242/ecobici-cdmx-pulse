"""Render the social preview image (docs/assets/og.png) from the exported trip sample."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

from . import config  # noqa: E402

COLORS = {0: "#22d3ee", 1: "#f472b6", 2: "#fbbf24"}


def render(path=None) -> str:
    path = path or config.ROOT / "docs" / "assets" / "og.png"
    trips = json.loads((config.SITE_DATA / "trips.json").read_text())
    stations = json.loads((config.SITE_DATA / "stations.json").read_text())
    meta = json.loads((config.SITE_DATA / "meta.json").read_text())
    k = len(trips["fields"])
    rows = np.array(trips["data"]).reshape(-1, k)

    fig = plt.figure(figsize=(12, 6.3), dpi=100, facecolor="#070b14")
    ax = fig.add_axes([0.38, 0.0, 0.62, 1.0], facecolor="#070b14")
    segs, cols = [], []
    for x0, y0, x1, y1, *_ , g in rows:
        dx, dy = x1 - x0, y1 - y0
        mx, my = (x0 + x1) / 2 - dy * 0.18, (y0 + y1) / 2 + dx * 0.18
        t = np.linspace(0, 1, 12)[:, None]
        p0, p1, p2 = np.array([x0, y0]), np.array([mx, my]), np.array([x1, y1])
        segs.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2)
        cols.append(COLORS[int(g)])
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=0.3, alpha=0.18))
    ax.scatter([s["lon"] for s in stations], [s["lat"] for s in stations], s=1.2, c="white", alpha=0.5)
    lon = np.array([s["lon"] for s in stations]); lat = np.array([s["lat"] for s in stations])
    ax.set_xlim(lon.min() - 0.01, lon.max() + 0.01); ax.set_ylim(lat.min() - 0.01, lat.max() + 0.01)
    ax.set_aspect(1 / np.cos(np.radians(19.4))); ax.axis("off")

    fig.text(0.05, 0.80, "ECOBICI CDMX PULSE", color="#22d3ee", fontsize=15, fontweight="bold")
    fig.text(0.05, 0.56, "El pulso de la\nCiudad de México\nen bicicleta", color="white",
             fontsize=34, fontweight="bold", linespacing=1.05, va="center")
    fig.text(0.05, 0.30, f"{meta['raw_trips'] / 1e6:.1f} M viajes · {meta['stations']} estaciones · 12 meses",
             color="#cbd5e1", fontsize=14)
    fig.text(0.05, 0.24, f"Pronóstico R² {meta['forecast_r2']:.2f} · anomalías · redes · WebGL",
             color="#94a3b8", fontsize=12)
    fig.text(0.05, 0.08, "Marco Osvaldo Murillo Arellano", color="#f472b6", fontsize=12)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return str(path)


if __name__ == "__main__":
    print(render())
