/* Ecobici CDMX Pulse — animated D3 charts. Each chart draws when it scrolls into view. */
window.PulseCharts = (() => {
  const C = { cyan: "#22d3ee", pink: "#f472b6", amber: "#fbbf24", red: "#f43f5e",
              blue: "#38bdf8", green: "#34d399", violet: "#a78bfa", muted: "#94a3b8", line: "rgba(148,163,184,.16)" };
  const CLUSTER = ["#22d3ee", "#f472b6", "#fbbf24", "#34d399", "#a78bfa", "#f87171", "#60a5fa"];
  const DOW = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
  const fmt = d3.format(","), pct = d3.format(".1f");
  const tip = document.getElementById("tooltip");
  let D;

  const showTip = (ev, html) => {
    tip.hidden = false; tip.innerHTML = html;
    const x = Math.min(ev.clientX + 14, innerWidth - 270);
    tip.style.left = `${x}px`; tip.style.top = `${ev.clientY + 14}px`;
  };
  const hideTip = () => (tip.hidden = true);

  function frame(sel, h, m = { t: 16, r: 16, b: 32, l: 48 }) {
    const el = document.querySelector(sel);
    el.innerHTML = "";
    const w = el.clientWidth;
    const svg = d3.select(el).append("svg").attr("width", w).attr("height", h).attr("viewBox", `0 0 ${w} ${h}`);
    return { svg, g: svg.append("g").attr("transform", `translate(${m.l},${m.t})`),
             w: w - m.l - m.r, h: h - m.t - m.b, m };
  }

  // ------------------------------------------------------------ heatmap hour × weekday
  function heatmap() {
    const data = D.heatmap.map(([dow, hr, v]) => ({ dow, hr, v }));
    const f = frame("#heatmap", 260, { t: 10, r: 10, b: 28, l: 40 });
    const x = d3.scaleBand().domain(d3.range(24)).range([0, f.w]).padding(0.08);
    const y = d3.scaleBand().domain(d3.range(1, 8)).range([0, f.h]).padding(0.08);
    const col = d3.scaleSequential(d3.interpolateInferno).domain([0, d3.max(data, (d) => d.v)]);
    f.g.append("g").attr("class", "axis").attr("transform", `translate(0,${f.h})`)
      .call(d3.axisBottom(x).tickValues(d3.range(0, 24, 3)).tickFormat((h) => `${h}h`).tickSize(0));
    f.g.append("g").attr("class", "axis").call(d3.axisLeft(y).tickFormat((d) => DOW[d - 1]).tickSize(0));
    f.g.selectAll("rect").data(data).join("rect")
      .attr("x", (d) => x(d.hr)).attr("y", (d) => y(d.dow)).attr("rx", 3)
      .attr("width", x.bandwidth()).attr("height", y.bandwidth()).attr("fill", "#111827")
      .on("mousemove", (ev, d) => showTip(ev, `<b>${DOW[d.dow - 1]} ${d.hr}:00</b><br>${fmt(Math.round(d.v))} viajes/h`))
      .on("mouseleave", hideTip)
      .transition().delay((d) => d.hr * 40 + d.dow * 25).duration(600).attr("fill", (d) => col(d.v));
  }

  // ------------------------------------------------------------ forecast with zoom
  function forecast() {
    const F = D.forecast, parse = d3.timeParse("%Y-%m-%dT%H");
    const rows = F.t.map((t, i) => ({ t: parse(t), a: F.actual[i], p: F.pred[i], b: F.base[i],
                                      dry: F.dry[i], rain: F.rain[i] }));
    document.getElementById("forecast-metrics").innerHTML = [
      [`${pct(F.metrics.r2 * 100)}%`, "varianza explicada (R²)"],
      [fmt(Math.round(F.metrics.mae)), "error medio (viajes/h)"],
      (() => { const g = (1 - F.metrics.mae / F.baseline_metrics.mae) * 100;
               return [`${pct(Math.abs(g))}%`, g >= 0 ? "menos error que el baseline" : "más error que el baseline"]; })(),
      [`${pct(F.rain_effect.pct_drop_in_rainy_hours)}%`, "caída de demanda en horas con lluvia"],
    ].map(([v, l]) => `<div class="metric"><b>${v}</b><span>${l}</span></div>`).join("");

    const f = frame("#forecast", 360, { t: 14, r: 16, b: 60, l: 52 });
    const ctxH = 34;
    const x = d3.scaleTime().domain(d3.extent(rows, (d) => d.t)).range([0, f.w]);
    const y = d3.scaleLinear().domain([0, d3.max(rows, (d) => Math.max(d.a, d.p, d.dry)) * 1.05]).nice().range([f.h - ctxH - 18, 0]);
    const yR = d3.scaleLinear().domain([0, d3.max(rows, (d) => d.rain) || 1]).range([0, 60]);
    const clip = f.svg.append("defs").append("clipPath").attr("id", "clip").append("rect").attr("width", f.w).attr("height", f.h);
    const main = f.g.append("g").attr("clip-path", "url(#clip)");
    const xAxis = f.g.append("g").attr("class", "axis").attr("transform", `translate(0,${y.range()[0]})`);
    f.g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(5).tickFormat(d3.format("~s")));
    f.g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(5).tickSize(-f.w).tickFormat(""));

    const rain = main.append("g");
    const area = (k) => d3.area().x((d) => x(d.t)).y0(y(0)).y1((d) => y(d[k])).curve(d3.curveMonotoneX);
    const line = (k) => d3.line().x((d) => x(d.t)).y((d) => y(d[k])).curve(d3.curveMonotoneX);
    const pActual = main.append("path").datum(rows).attr("fill", "rgba(34,211,238,.12)").attr("stroke", C.cyan).attr("stroke-width", 1.4);
    const pDry = main.append("path").datum(rows).attr("fill", "none").attr("stroke", C.amber).attr("stroke-width", 1).attr("stroke-dasharray", "2 3").attr("opacity", .8);
    const pPred = main.append("path").datum(rows).attr("fill", "none").attr("stroke", C.pink).attr("stroke-width", 1.6);

    function draw() {
      xAxis.call(d3.axisBottom(x).ticks(6).tickFormat(d3.timeFormat("%d %b")));
      pActual.attr("d", area("a")); pPred.attr("d", line("p")); pDry.attr("d", line("dry"));
      rain.selectAll("rect").data(rows.filter((d) => d.rain > 0.2)).join("rect")
        .attr("x", (d) => x(d.t)).attr("width", Math.max(1, x(d3.timeHour.offset(rows[0].t, 1)) - x(rows[0].t)))
        .attr("y", 0).attr("height", (d) => yR(d.rain)).attr("fill", "rgba(56,189,248,.35)");
    }
    draw();
    // Draw-in animation of the prediction line.
    const L = pPred.node().getTotalLength();
    pPred.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L)
      .transition().duration(2600).ease(d3.easeCubicInOut).attr("stroke-dashoffset", 0)
      .on("end", () => pPred.attr("stroke-dasharray", null));

    // Context strip with brush to zoom.
    const x2 = d3.scaleTime().domain(x.domain()).range([0, f.w]);
    const y2 = d3.scaleLinear().domain(y.domain()).range([ctxH, 0]);
    const ctx = f.g.append("g").attr("transform", `translate(0,${f.h - ctxH + 18})`);
    ctx.append("path").datum(rows).attr("fill", "rgba(34,211,238,.25)")
      .attr("d", d3.area().x((d) => x2(d.t)).y0(ctxH).y1((d) => y2(d.a)));
    const brush = d3.brushX().extent([[0, 0], [f.w, ctxH]]).on("brush end", ({ selection }) => {
      x.domain(selection ? selection.map(x2.invert) : x2.domain()); draw();
    });
    const start = x2(d3.timeDay.offset(x2.domain()[1], -7));
    ctx.append("g").call(brush).call(brush.move, [start, f.w])
      .selectAll(".selection").attr("fill", C.cyan).attr("fill-opacity", .18).attr("stroke", C.cyan);

    const legend = [["Real", C.cyan], ["Pronóstico", C.pink], ["Si no hubiera llovido", C.amber], ["Lluvia (mm)", C.blue]];
    const itemW = Math.min(150, (f.w + f.m.l) / 2), perRow = Math.max(1, Math.floor((f.w + f.m.l) / itemW));
    f.svg.append("g").attr("transform", `translate(${f.m.l / 2},${f.h + f.m.t + 34})`).selectAll("g").data(legend).join("g")
      .attr("transform", (d, i) => `translate(${(i % perRow) * itemW},${Math.floor(i / perRow) * 16})`)
      .call((g) => { g.append("rect").attr("width", 10).attr("height", 10).attr("y", -9).attr("rx", 2).attr("fill", (d) => d[1]);
                     g.append("text").attr("x", 15).text((d) => d[0]); });

    // Hover readout.
    const hover = main.append("line").attr("stroke", C.muted).attr("y1", 0).attr("y2", y.range()[0]).attr("opacity", 0);
    f.g.append("rect").attr("width", f.w).attr("height", y.range()[0]).attr("fill", "transparent")
      .on("mousemove", (ev) => {
        const t = x.invert(d3.pointer(ev)[0]);
        const d = rows[Math.max(0, d3.bisector((r) => r.t).center(rows, t))];
        hover.attr("x1", x(d.t)).attr("x2", x(d.t)).attr("opacity", 1);
        showTip(ev, `<b>${d3.timeFormat("%a %d %b, %H:00")(d.t)}</b><br>Real: ${fmt(d.a)}<br>Pronóstico: ${fmt(d.p)}${d.rain > 0.2 ? `<br>Lluvia: ${d.rain} mm` : ""}`);
      })
      .on("mouseleave", () => { hover.attr("opacity", 0); hideTip(); });

    // Model comparison (rolling-origin CV).
    const cv = F.cv;
    const g2 = frame("#model-compare", 150, { t: 24, r: 90, b: 10, l: 170 });
    const xs = d3.scaleLinear().domain([0, d3.max(cv, (d) => d.mae)]).range([0, g2.w]);
    const ys = d3.scaleBand().domain(cv.map((d) => d.model)).range([0, g2.h]).padding(.3);
    g2.svg.append("text").attr("class", "title").attr("x", 4).attr("y", 14).text("Validación rolling-origin · error medio (menor es mejor)");
    g2.g.append("g").attr("class", "axis").call(d3.axisLeft(ys).tickSize(0)).selectAll("text").style("fill", "#e6ebf5");
    g2.g.selectAll("rect").data(cv).join("rect").attr("y", (d) => ys(d.model)).attr("height", ys.bandwidth()).attr("rx", 4)
      .attr("fill", (d, i) => (i === 0 ? C.pink : "#334155")).attr("width", 0)
      .transition().duration(1200).attr("width", (d) => xs(d.mae));
    g2.g.selectAll(".v").data(cv).join("text").attr("class", "v").attr("x", (d) => xs(d.mae) + 6)
      .attr("y", (d) => ys(d.model) + ys.bandwidth() / 2 + 4).text((d) => `${fmt(Math.round(d.mae))} viajes/h`);
  }

  // ------------------------------------------------------------ calendar of anomalies
  function calendar() {
    const rows = D.daily.map((d) => ({ ...d, date: new Date(d.d + "T12:00") }));
    const el = document.querySelector("#calendar"), w = el.clientWidth;
    const weeks = d3.timeWeek.count(rows[0].date, rows[rows.length - 1].date) + 1;
    const cell = Math.max(8, Math.min(18, Math.floor((w - 40) / weeks)));
    const f = frame("#calendar", cell * 7 + 46, { t: 22, r: 10, b: 20, l: 34 });
    const col = d3.scaleDiverging(d3.interpolateRdBu).domain([-45, 0, 45]);
    const x = (d) => d3.timeWeek.count(rows[0].date, d.date) * cell;
    const yy = (d) => ((d.date.getDay() + 6) % 7) * cell;
    f.g.selectAll(".dl").data(DOW).join("text").attr("class", "dl").attr("x", -6).attr("text-anchor", "end")
      .attr("y", (d, i) => i * cell + cell * .75).text((d, i) => (i % 2 ? "" : d));
    const months = d3.timeMonths(rows[0].date, rows[rows.length - 1].date);
    f.g.selectAll(".ml").data(months).join("text").attr("class", "ml").attr("y", -8)
      .attr("x", (m) => d3.timeWeek.count(rows[0].date, m) * cell).text(d3.timeFormat("%b"));
    f.g.selectAll("rect").data(rows).join("rect")
      .attr("x", x).attr("y", yy).attr("width", cell - 2).attr("height", cell - 2).attr("rx", 2)
      .attr("fill", "#111827").attr("stroke", (d) => (d.an ? "#fff" : "none")).attr("stroke-width", 1.6)
      .on("mousemove", (ev, d) => {
        const r = ((d.a - d.e) / d.e) * 100;
        showTip(ev, `<b>${d3.timeFormat("%A %d %b %Y")(d.date)}</b><br>Real ${fmt(d.a)} · esperado ${fmt(d.e)}<br>${r > 0 ? "+" : ""}${pct(r)}% · z = ${d.z}${d.p ? `<br>Lluvia ${d.p} mm` : ""}${d.x ? `<br><b>${d.x}</b>` : ""}`);
      })
      .on("mouseleave", hideTip)
      .transition().delay((d, i) => i * 4).duration(400)
      .attr("fill", (d) => col(((d.a - d.e) / d.e) * 100));
  }

  // ------------------------------------------------------------ bars helper
  function bars(sel, data, { x, y, color, label, title, fmtV = (v) => v }) {
    const f = frame(sel, 220, { t: 26, r: 14, b: 36, l: 46 });
    const xs = d3.scaleBand().domain(data.map(x)).range([0, f.w]).padding(.28);
    const ys = d3.scaleLinear().domain([0, d3.max(data, y) * 1.15]).nice().range([f.h, 0]);
    f.g.append("text").attr("class", "title").attr("y", -10).text(title);
    f.g.append("g").attr("class", "axis").attr("transform", `translate(0,${f.h})`).call(d3.axisBottom(xs).tickSize(0));
    f.g.append("g").attr("class", "grid").call(d3.axisLeft(ys).ticks(4).tickSize(-f.w).tickFormat(""));
    f.g.selectAll("rect").data(data).join("rect").attr("x", (d) => xs(x(d))).attr("width", xs.bandwidth())
      .attr("y", f.h).attr("height", 0).attr("rx", 5).attr("fill", color)
      .transition().duration(900).delay((d, i) => i * 120).attr("y", (d) => ys(y(d))).attr("height", (d) => f.h - ys(y(d)));
    f.g.selectAll(".v").data(data).join("text").attr("class", "v").attr("text-anchor", "middle")
      .attr("x", (d) => xs(x(d)) + xs.bandwidth() / 2).attr("y", (d) => ys(y(d)) - 6).style("fill", "#e6ebf5")
      .text((d) => label(d));
  }

  function environment() {
    const order = ["0", "<1", "1-3", "3-6", "6+"];
    const rain = D.environment.rain.filter((d) => order.includes(d.rain_bin))
      .sort((a, b) => order.indexOf(a.rain_bin) - order.indexOf(b.rain_bin));
    const dry = rain.find((d) => d.rain_bin === "0");
    const worst = rain[rain.length - 1];
    document.getElementById("rain-text").innerHTML =
      `Frente a una hora seca equivalente (misma hora, día y mes), con lluvia de ${worst.rain_bin} mm la demanda cae a <b>${pct(worst.ratio_vs_dry * 100)}%</b> de lo normal. El modelo estima que la lluvia resta <b>${pct(D.forecast.rain_effect.pct_drop_in_rainy_hours)}%</b> de los viajes en las horas en que llueve.`;
    bars("#rain-chart", rain, { x: (d) => `${d.rain_bin} mm`, y: (d) => d.ratio_vs_dry * 100,
      color: (d) => (d.rain_bin === "0" ? C.cyan : C.blue), label: (d) => `${Math.round(d.ratio_vs_dry * 100)}%`,
      title: "Demanda vs. hora seca equivalente" });
    const aqOrder = ["Buena", "Aceptable", "Mala (sensibles)", "Mala"];
    const aqi = D.environment.aqi.sort((a, b) => aqOrder.indexOf(a.aqi_bin) - aqOrder.indexOf(b.aqi_bin));
    bars("#aqi-chart", aqi, { x: (d) => d.aqi_bin, y: (d) => d.ratio_vs_typical * 100,
      color: (d, i) => [C.green, C.amber, "#fb923c", C.red][aqOrder.indexOf(d.aqi_bin)],
      label: (d) => `${Math.round(d.ratio_vs_typical * 100)}%`, title: "Demanda vs. lo típico para esa hora" });
  }

  function riders() {
    const bh = D.riders.by_hour.filter((d) => d.trips > 500);
    const f = frame("#gender-hour", 220, { t: 20, r: 14, b: 30, l: 40 });
    const x = d3.scaleLinear().domain([0, 23]).range([0, f.w]);
    const y = d3.scaleLinear().domain([d3.min(bh, (d) => d.pct_women) - 3, d3.max(bh, (d) => d.pct_women) + 3]).range([f.h, 0]);
    f.g.append("g").attr("class", "axis").attr("transform", `translate(0,${f.h})`).call(d3.axisBottom(x).ticks(8).tickFormat((h) => `${h}h`));
    f.g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(4).tickFormat((v) => `${v}%`));
    const p = f.g.append("path").datum(bh).attr("fill", "none").attr("stroke", C.pink).attr("stroke-width", 2.5)
      .attr("d", d3.line().x((d) => x(d.hour_of_day)).y((d) => y(d.pct_women)).curve(d3.curveCatmullRom));
    const L = p.node().getTotalLength();
    p.attr("stroke-dasharray", `${L} ${L}`).attr("stroke-dashoffset", L).transition().duration(1800).attr("stroke-dashoffset", 0);
    f.g.selectAll("circle").data(bh).join("circle").attr("cx", (d) => x(d.hour_of_day)).attr("cy", (d) => y(d.pct_women))
      .attr("r", 3).attr("fill", C.pink)
      .on("mousemove", (ev, d) => showTip(ev, `<b>${d.hour_of_day}:00</b><br>${pct(d.pct_women)}% mujeres`)).on("mouseleave", hideTip);

    const tbl = D.riders.table.filter((d) => d.age_band !== "ND" && d.gender !== "O/ND");
    const bands = ["16-24", "25-34", "35-44", "45-54", "55+"];
    const g = frame("#age-chart", 220, { t: 20, r: 14, b: 30, l: 46 });
    const x0 = d3.scaleBand().domain(bands).range([0, g.w]).padding(.2);
    const x1 = d3.scaleBand().domain(["F", "M"]).range([0, x0.bandwidth()]).padding(.1);
    const yy = d3.scaleLinear().domain([0, d3.max(tbl, (d) => d.trips)]).nice().range([g.h, 0]);
    g.g.append("g").attr("class", "axis").attr("transform", `translate(0,${g.h})`).call(d3.axisBottom(x0).tickSize(0));
    g.g.append("g").attr("class", "axis").call(d3.axisLeft(yy).ticks(4).tickFormat(d3.format("~s")));
    g.g.selectAll("rect").data(tbl).join("rect").attr("x", (d) => x0(d.age_band) + x1(d.gender)).attr("width", x1.bandwidth())
      .attr("y", g.h).attr("height", 0).attr("rx", 3).attr("fill", (d) => (d.gender === "F" ? C.pink : C.cyan))
      .on("mousemove", (ev, d) => showTip(ev, `<b>${d.gender === "F" ? "Mujeres" : "Hombres"} ${d.age_band}</b><br>${fmt(d.trips)} viajes<br>Mediana ${pct(d.median_duration_min)} min`))
      .on("mouseleave", hideTip)
      .transition().duration(900).delay((d, i) => i * 60).attr("y", (d) => yy(d.trips)).attr("height", (d) => g.h - yy(d.trips));
  }

  function clusters() {
    const c = D.clusters;
    const f = frame("#cluster-chart", 200, { t: 10, r: 8, b: 26, l: 30 });
    const x = d3.scaleLinear().domain([0, 23]).range([0, f.w]);
    // centroid = 24 departures + 24 arrivals (normalised); plot departures - arrivals.
    const series = c.centroids.map((v, i) => ({ i, pts: d3.range(24).map((h) => ({ h, v: (v[h] - v[24 + h]) * 100 })) }));
    const ext = d3.extent(series.flatMap((s) => s.pts.map((p) => p.v)));
    const y = d3.scaleLinear().domain(ext).nice().range([f.h, 0]);
    f.g.append("g").attr("class", "axis").attr("transform", `translate(0,${f.h})`).call(d3.axisBottom(x).ticks(6).tickFormat((h) => `${h}h`));
    f.g.append("line").attr("x1", 0).attr("x2", f.w).attr("y1", y(0)).attr("y2", y(0)).attr("stroke", C.muted).attr("stroke-dasharray", "3 3");
    f.g.append("text").attr("x", 4).attr("y", 10).text("↑ más salidas").attr("font-size", 10);
    f.g.append("text").attr("x", 4).attr("y", f.h - 4).text("↓ más llegadas").attr("font-size", 10);
    series.forEach((s) => {
      f.g.append("path").datum(s.pts).attr("fill", "none").attr("stroke", CLUSTER[s.i]).attr("stroke-width", 2.2)
        .attr("d", d3.line().x((p) => x(p.h)).y((p) => y(p.v)).curve(d3.curveCatmullRom))
        .on("mousemove", (ev) => showTip(ev, `<b>${c.names[s.i]}</b><br>${c.sizes[s.i]} estaciones`)).on("mouseleave", hideTip);
    });
  }

  // ------------------------------------------------------------ lazy init
  function init(data) {
    D = data;
    const draws = { "#heatmap": heatmap, "#forecast": forecast, "#calendar": calendar,
                    "#rain-chart": environment, "#gender-hour": riders, "#cluster-chart": clusters };
    const drawn = new Set();
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      const key = "#" + e.target.id;
      if (e.isIntersecting && !drawn.has(key)) { drawn.add(key); draws[key](); }
    }), { threshold: 0.2 });
    Object.keys(draws).forEach((k) => io.observe(document.querySelector(k)));
    let t;
    addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => drawn.forEach((k) => draws[k]()), 300); });
  }

  return { init };
})();
