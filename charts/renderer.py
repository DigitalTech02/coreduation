"""Render a D3 chart to PNG using a headless Chromium (Playwright).

Falls back gracefully when Playwright isn't installed or browsers aren't
provisioned: returns ``None`` so the Manim engine can show a stylised table
instead.

The output PNG is cached by ``(chart_type, title, labels, series, series_labels)``
so repeated calls are free.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

ASSETS_CHART_DIR = Path("assets/charts")

# Self-contained HTML template with inline D3 (loaded from CDN).
_TEMPLATE = """\
<!doctype html>
<html><head><meta charset='utf-8'>
<script src='https://cdn.jsdelivr.net/npm/d3@7'></script>
<style>
  body { margin: 0; background: #0f1117; color: #e6edf3;
         font-family: 'Inter', system-ui, sans-serif; }
  svg  { display: block; }
  .axis text { fill: #98a3b3; font-size: 14px; }
  .axis path, .axis line { stroke: #313844; }
  .title { font-size: 28px; font-weight: 700; fill: #ffffff; }
</style></head><body>
<div id='root'></div>
<script>
const SPEC = __SPEC__;
const W = SPEC.width || 1280, H = SPEC.height || 720, M = {top: 80, right: 60, bottom: 80, left: 80};
const root = d3.select('#root').append('svg').attr('width', W).attr('height', H);
root.append('text').attr('class','title').attr('x', M.left).attr('y', 50).text(SPEC.title || '');

function bar(spec) {
  const x = d3.scaleBand().domain(spec.labels).range([M.left, W - M.right]).padding(0.25);
  const y = d3.scaleLinear().domain([0, d3.max(spec.series) * 1.1]).range([H - M.bottom, M.top + 20]);
  root.append('g').attr('class','axis').attr('transform', `translate(0,${H - M.bottom})`).call(d3.axisBottom(x));
  root.append('g').attr('class','axis').attr('transform', `translate(${M.left},0)`).call(d3.axisLeft(y).ticks(6));
  root.append('g').selectAll('rect').data(spec.series).enter().append('rect')
    .attr('x', (_,i) => x(spec.labels[i]))
    .attr('width', x.bandwidth())
    .attr('y', d => y(d))
    .attr('height', d => H - M.bottom - y(d))
    .attr('fill', spec.color || '#3FB6FF')
    .attr('rx', 6);
}
function line(spec) {
  const x = d3.scalePoint().domain(spec.labels).range([M.left, W - M.right]);
  const y = d3.scaleLinear().domain([0, d3.max(spec.series) * 1.1]).range([H - M.bottom, M.top + 20]);
  root.append('g').attr('class','axis').attr('transform', `translate(0,${H - M.bottom})`).call(d3.axisBottom(x));
  root.append('g').attr('class','axis').attr('transform', `translate(${M.left},0)`).call(d3.axisLeft(y).ticks(6));
  const ln = d3.line().x((_,i)=>x(spec.labels[i])).y(d=>y(d)).curve(d3.curveCatmullRom);
  root.append('path').datum(spec.series)
    .attr('fill','none').attr('stroke', spec.color || '#3FB6FF').attr('stroke-width', 4).attr('d', ln);
}
function donut(spec) {
  const total = d3.sum(spec.series);
  const cx = W/2, cy = H/2 + 20, r = Math.min(W, H) * 0.28;
  const pie = d3.pie()(spec.series);
  const arc = d3.arc().innerRadius(r * 0.55).outerRadius(r);
  const palette = ['#3FB6FF', '#B388FF', '#86E27A', '#FFD93D', '#FF6B6B', '#4DD0E1'];
  const g = root.append('g').attr('transform', `translate(${cx},${cy})`);
  g.selectAll('path').data(pie).enter().append('path')
    .attr('d', arc).attr('fill', (_,i) => palette[i % palette.length]);
  if (spec.series_labels && spec.series_labels.length) {
    const lg = root.append('g').attr('transform', `translate(${W - 280},${M.top + 60})`);
    spec.series_labels.forEach((lbl, i) => {
      lg.append('rect').attr('x', 0).attr('y', i*30).attr('width', 18).attr('height', 18)
        .attr('fill', palette[i % palette.length]);
      lg.append('text').attr('x', 28).attr('y', i*30 + 14)
        .attr('fill', '#e6edf3').attr('font-size', 16)
        .text(`${lbl}: ${Math.round(spec.series[i] / total * 100)}%`);
    });
  }
}
const handler = ({bar, line, donut})[SPEC.chart_type] || bar;
handler(SPEC);
</script></body></html>
"""


def _hash(*parts) -> str:
    import hashlib
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:24]


def render_chart_to_image(
    chart_type: str,
    title: str,
    labels: list[str],
    series: list[float],
    series_labels: list[str] | None = None,
    width: int = 1280,
    height: int = 720,
) -> str | None:
    """Render a D3 chart to PNG; return path or None on failure."""
    ASSETS_CHART_DIR.mkdir(parents=True, exist_ok=True)
    spec = {
        "chart_type": chart_type,
        "title": title,
        "labels": labels,
        "series": series,
        "series_labels": series_labels or [],
        "width": width,
        "height": height,
    }
    key = _hash(spec)
    out = ASSETS_CHART_DIR / f"{key}.png"
    if out.is_file():
        return str(out)

    html = _TEMPLATE.replace("__SPEC__", json.dumps(spec))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("Playwright not installed — skipping D3 chart render")
        return None

    work = Path(tempfile.mkdtemp(prefix="chart_"))
    html_file = work / "chart.html"
    html_file.write_text(html, encoding="utf-8")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(html_file.as_uri())
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(out), omit_background=False)
            browser.close()
    except Exception as e:
        logger.warning("Playwright chart render failed: %s", e)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return str(out) if out.is_file() else None
