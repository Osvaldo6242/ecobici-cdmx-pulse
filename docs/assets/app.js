/* Ecobici CDMX Pulse — map, WebGL layers and scroll-driven story. */
(() => {
  const { MapboxOverlay, TripsLayer, ColumnLayer, ArcLayer, ScatterplotLayer } = deck;

  const COLORS = {
    m: [34, 211, 238], f: [244, 114, 182], o: [251, 191, 36],
    red: [244, 63, 94], blue: [56, 189, 248],
  };
  const COMMUNITY = [[34,211,238],[244,114,182],[251,191,36],[52,211,153],[167,139,250],
                     [248,113,113],[96,165,250],[250,204,21],[45,212,191],[232,121,249]];
  const CLUSTER = [[34,211,238],[244,114,182],[251,191,36],[52,211,153],[167,139,250],[248,113,113],[96,165,250]];
  const VIEWS = {
    trips:     { center: [-99.172, 19.413], zoom: 12.6, pitch: 45, bearing: -18 },
    columns:   { center: [-99.170, 19.418], zoom: 13.1, pitch: 58, bearing: 24 },
    flows:     { center: [-99.172, 19.405], zoom: 12.4, pitch: 50, bearing: -10 },
    clusters:  { center: [-99.172, 19.405], zoom: 12.5, pitch: 0, bearing: 0 },
    rebalance: { center: [-99.170, 19.412], zoom: 12.9, pitch: 30, bearing: 8 },
  };
  const isMobile = matchMedia("(max-width: 760px)").matches;
  const fmt = d3.format(",");
  const pad = (n) => String(n).padStart(2, "0");
  const hhmm = (s) => `${pad(Math.floor(s / 3600) % 24)}:${pad(Math.floor(s / 60) % 60)}`;

  const state = { mode: "trips", time: 6 * 3600, hour: 8, playing: true, hourPlaying: true, data: {} };
  let overlay, map;

  // ------------------------------------------------------------------ data
  async function load() {
    const names = ["meta", "stations", "trips", "flows", "forecast", "daily", "heatmap",
                   "environment", "clusters", "riders"];
    const res = await Promise.all(names.map((n) => fetch(`data/${n}.json`).then((r) => r.json())));
    names.forEach((n, i) => (state.data[n] = res[i]));

    // Rebuild trips as curved 3-point paths.
    const t = state.data.trips, F = t.fields.length, out = [];
    for (let i = 0; i < t.data.length; i += F) {
      const [x0, y0, x1, y1, t0, t1, g] = t.data.slice(i, i + F);
      const dx = x1 - x0, dy = y1 - y0, k = ((i / F) % 2 ? 1 : -1) * 0.18;
      out.push({
        path: [[x0, y0], [(x0 + x1) / 2 - dy * k, (y0 + y1) / 2 + dx * k], [x1, y1]],
        ts: [t0, (t0 + t1) / 2, t1], g,
      });
    }
    state.trips = out;                                   // already sorted by start time
    state.scale = t.total_trips_that_day / Math.max(t.sampled, 1);
    state.stationById = new Map(state.data.stations.map((s) => [s.id, s]));
  }

  // ------------------------------------------------------------------ layers
  function layers() {
    const d = state.data, L = [];
    if (state.mode === "trips") {
      L.push(new TripsLayer({
        id: "trips", data: state.trips,
        getPath: (x) => x.path, getTimestamps: (x) => x.ts,
        getColor: (x) => (x.g === 1 ? COLORS.f : x.g === 0 ? COLORS.m : COLORS.o),
        opacity: 0.85, widthMinPixels: 2, jointRounded: true, capRounded: true,
        trailLength: 480, currentTime: state.time, fadeTrail: true,
      }));
      L.push(stationDots(18, [255, 255, 255, 60]));
    }
    if (state.mode === "columns") {
      const max = d3.max(d.stations, (s) => d3.max(s.dep || [0])) || 1;
      const color = d3.scaleSequential(d3.interpolatePlasma).domain([0, max * 0.7]);
      L.push(new ColumnLayer({
        id: "columns", data: d.stations.filter((s) => s.dep.length),
        diskResolution: 12, radius: 70, extruded: true, elevationScale: 55,
        getPosition: (s) => [s.lon, s.lat],
        getElevation: (s) => s.dep[state.hour],
        getFillColor: (s) => { const c = d3.color(color(s.dep[state.hour])); return [c.r, c.g, c.b, 230]; },
        updateTriggers: { getElevation: state.hour, getFillColor: state.hour },
        transitions: { getElevation: 700, getFillColor: 700 },
        pickable: true,
      }));
    }
    if (state.mode === "flows") {
      const w = d3.scaleSqrt().domain([0, d3.max(d.flows, (f) => f.v)]).range([0.6, 9]);
      L.push(new ArcLayer({
        id: "flows", data: d.flows,
        getSourcePosition: (f) => f.s, getTargetPosition: (f) => f.t,
        getSourceColor: (f) => [...COMMUNITY[Math.max(f.cm, 0) % COMMUNITY.length], 210],
        getTargetColor: (f) => [...COMMUNITY[Math.max(f.cm, 0) % COMMUNITY.length], 90],
        getWidth: (f) => w(f.v), getHeight: 0.5, pickable: true,
      }));
      L.push(stationDots(22, [255, 255, 255, 50]));
    }
    if (state.mode === "clusters") {
      L.push(new ScatterplotLayer({
        id: "clusters", data: d.stations.filter((s) => s.cl !== null),
        getPosition: (s) => [s.lon, s.lat], getRadius: 85, radiusMinPixels: 3,
        getFillColor: (s) => [...CLUSTER[s.cl % CLUSTER.length], 225],
        stroked: true, getLineColor: [7, 11, 20], lineWidthMinPixels: 1, pickable: true,
      }));
    }
    if (state.mode === "rebalance") {
      L.push(new ScatterplotLayer({
        id: "rebalance", data: d.stations.filter((s) => s.risk !== null),
        getPosition: (s) => [s.lon, s.lat],
        getRadius: (s) => 40 + Math.sqrt(s.risk) * 130, radiusMinPixels: 2,
        getFillColor: (s) => [...(s.rt === "se vacía" ? COLORS.red : COLORS.blue), 150],
        stroked: true, getLineColor: (s) => [...(s.rt === "se vacía" ? COLORS.red : COLORS.blue), 255],
        lineWidthMinPixels: 1, pickable: true,
      }));
    }
    return L;
  }

  function stationDots(r, color) {
    return new ScatterplotLayer({
      id: "dots", data: state.data.stations, getPosition: (s) => [s.lon, s.lat],
      getRadius: r, radiusMinPixels: 1, getFillColor: color,
    });
  }

  function tooltip({ object, layer }) {
    if (!object) return null;
    if (layer.id === "columns")
      return { html: `<b>${object.n}</b><br>${hhmm(state.hour * 3600)} · ${object.dep[state.hour].toFixed(1)} salidas/h` };
    if (layer.id === "flows")
      return { html: `<b>${object.v} viajes/día laboral</b><br>${object.km} km en línea recta` };
    if (layer.id === "clusters")
      return { html: `<b>${object.n}</b><br>${state.data.clusters.names[object.cl]}` };
    if (layer.id === "rebalance")
      return { html: `<b>${object.n}</b><br>${object.rt} · presión ${object.risk}× su capacidad` };
    return null;
  }

  const render = () => overlay && overlay.setProps({ layers: layers() });

  // ------------------------------------------------------------------ animation
  let last = performance.now();
  function tick(now) {
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;
    if (state.mode === "trips" && state.playing) {
      state.time += dt * 600;                      // 10 minutes per second
      if (state.time > 24 * 3600) state.time = 5 * 3600;
      document.getElementById("clock").textContent = hhmm(state.time);
      // Bikes on the road right now, scaled from the sample to the full day.
      let n = 0;
      for (const t of state.trips) { if (t.ts[0] > state.time) break; if (t.ts[2] >= state.time) n++; }
      document.getElementById("active").textContent = `${fmt(Math.round(n * state.scale))} bicis en ruta`;
      render();
    }
    requestAnimationFrame(tick);
  }

  let hourTimer;
  function setHour(h) {
    state.hour = h;
    document.getElementById("hour-slider").value = h;
    document.getElementById("hour-label").textContent = `${pad(h)}:00`;
    document.getElementById("clock").textContent = `${pad(h)}:00`;
    render();
  }
  function startHourLoop() {
    clearInterval(hourTimer);
    if (!state.hourPlaying) return;
    hourTimer = setInterval(() => setHour((state.hour + 1) % 24), 1100);
  }

  // ------------------------------------------------------------------ legend / HUD
  function setLegend(mode) {
    const el = document.getElementById("legend"), lab = document.getElementById("hud-label");
    const item = (c, t) => `<div class="item">${t}<span class="sw" style="background:rgb(${c})"></span></div>`;
    const map_ = {
      trips: ["Viajes en curso", item(COLORS.f, "Mujeres") + item(COLORS.m, "Hombres") + item(COLORS.o, "Sin dato")],
      columns: ["Salidas por hora", ""],
      flows: ["Flujos origen-destino", ""],
      clusters: ["Arquetipos", state.data.clusters.names.map((n, i) => item(CLUSTER[i], n)).join("")],
      rebalance: ["Presión de rebalanceo", item(COLORS.red, "Se vacía") + item(COLORS.blue, "Se llena")],
    };
    lab.textContent = map_[mode][0];
    el.innerHTML = map_[mode][1];
  }

  function setMode(mode) {
    if (state.mode === mode) return;
    state.mode = mode;
    const v = VIEWS[mode];
    map.flyTo({ ...v, zoom: v.zoom - (isMobile ? 1 : 0), duration: 2200, essential: true });
    document.getElementById("hour-control").hidden = mode !== "columns";
    document.getElementById("clock").style.visibility = mode === "trips" || mode === "columns" ? "visible" : "hidden";
    document.getElementById("active").style.visibility = mode === "trips" ? "visible" : "hidden";
    if (mode === "columns") { setHour(state.hour); startHourLoop(); } else clearInterval(hourTimer);
    setLegend(mode);
    render();
  }

  // ------------------------------------------------------------------ text fill-ins
  function fillText() {
    const m = state.data.meta, t = state.data.trips;
    document.getElementById("k-trips").textContent = fmt(m.raw_trips);
    const dayFmt = new Date(t.day + "T12:00").toLocaleDateString("es-MX", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    document.getElementById("s-day").textContent = dayFmt;
    document.getElementById("s-day-trips").textContent = `${fmt(t.total_trips_that_day)} (se muestran ${fmt(t.sampled)})`;
    document.getElementById("s-peak").textContent = `${pad(m.busiest_hour)}:00`;
    document.getElementById("s-mod").textContent = m.modularity;
    document.getElementById("s-comm").textContent = m.communities;
    document.getElementById("s-k").textContent = m.clusters_k;
    document.getElementById("r-women").textContent = `${m.pct_women}%`;
    const bad = m.dq.filter((r) => r.validity !== "valid").reduce((a, r) => a + r.trips, 0);
    document.getElementById("dq-text").textContent =
      `${fmt(m.raw_trips)} registros auditados; ${fmt(bad)} descartados (${(100 - m.pct_valid).toFixed(2)}%) por duración imposible, timestamps ilegibles, fuera de ventana o estación desconocida.`;

    const top = state.data.stations.filter((s) => s.risk !== null)
      .sort((a, b) => b.risk - a.risk).slice(0, 6);
    document.getElementById("rebalance-list").innerHTML = top
      .map((s) => `<li>${s.n} — <span style="color:${s.rt === "se vacía" ? "var(--red)" : "var(--blue)"}">${s.rt}</span> (${s.risk}×)</li>`).join("");

    document.querySelectorAll(".kpis .num").forEach((el) => {
      const target = m[el.dataset.key], dec = +(el.dataset.dec || 0);
      d3.select(el).transition().duration(2200).ease(d3.easeCubicOut)
        .tween("text", () => { const i = d3.interpolateNumber(0, target);
          return (p) => (el.textContent = dec ? i(p).toFixed(dec) : fmt(Math.round(i(p)))); });
    });
  }

  // ------------------------------------------------------------------ boot
  async function init() {
    await load();
    map = new maplibregl.Map({
      container: "map",
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      ...VIEWS.trips, zoom: VIEWS.trips.zoom - (isMobile ? 1 : 0),
      interactive: false, attributionControl: { compact: true },
    });
    overlay = new MapboxOverlay({ interleaved: false, layers: layers(), getTooltip: tooltip });
    map.addControl(overlay);
    setLegend("trips");
    fillText();
    requestAnimationFrame(tick);

    const scroller = scrollama();
    scroller.setup({ step: ".step", offset: 0.6 })
      .onStepEnter(({ element }) => {
        document.querySelectorAll(".step").forEach((s) => s.classList.toggle("is-active", s === element));
        setMode(element.dataset.step);
      });
    window.addEventListener("resize", () => scroller.resize());

    // Hero counts as the trips step.
    new IntersectionObserver(([e]) => { if (e.isIntersecting) setMode("trips"); }, { threshold: 0.5 })
      .observe(document.getElementById("hero"));

    // Fade the map and pause animation once the chart section takes over.
    new IntersectionObserver(([e]) => {
      const on = e.isIntersecting;
      document.getElementById("map-wrap").classList.toggle("faded", on);
      state.playing = !on;
    }, { rootMargin: "-40% 0px 0px 0px" }).observe(document.getElementById("charts"));

    document.getElementById("hour-slider").addEventListener("input", (e) => {
      state.hourPlaying = false; document.getElementById("hour-play").textContent = "▶";
      clearInterval(hourTimer); setHour(+e.target.value);
    });
    document.getElementById("hour-play").addEventListener("click", (e) => {
      state.hourPlaying = !state.hourPlaying;
      e.target.textContent = state.hourPlaying ? "❚❚" : "▶";
      startHourLoop();
    });

    window.PulseCharts.init(state.data);
  }

  init().catch((err) => {
    console.error(err);
    document.getElementById("hero").insertAdjacentHTML("beforeend",
      `<p style="color:#f43f5e">No se pudieron cargar los datos: ${err.message}</p>`);
  });
})();
