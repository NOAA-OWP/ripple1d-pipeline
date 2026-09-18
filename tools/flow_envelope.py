#!/usr/bin/env python3
"""
Fully AI Generated

flow_envelope.py — Generate an interactive flow-envelope HTML chart from a
ripple1d-style GeoPackage.

The GPKG must contain a `scenarios` table with columns:
    reach_id, us_flow, ds_wse, boundary_condition
(the standard ripple1d schema). One chart is produced with:
  * X = discharge (us_flow, cfs), Y = downstream WSEL (ds_wse, ft)
  * a shaded envelope band per reach (min..max ds_wse at each flow)
  * the normal-depth ("nd") rating curve as a solid line
  * every computed point as a marker
  * per-reach toggles, auto-rescaling axes, hover tooltips, and a table view

Usage
-----
    python flow_envelope.py RIPPLE.gpkg 6211748:headwater 6212600:interior 6211758:outlet
    python flow_envelope.py RIPPLE.gpkg 6211748 6212600 6211758 -o out.html --title "MIP 02020008"

Each REACH argument is either  <reach_id>  or  <reach_id>:<label>.
Only the Python standard library is required (sqlite3, argparse, json).
"""

import argparse
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path

# --- Validated categorical palette (dataviz reference palette, slots 1-8) -----
# Light hex / dark hex, in fixed CVD-safe order. Do not re-order.
PALETTE = [
    ("#2a78d6", "#3987e5"),  # 1 blue
    ("#008300", "#008300"),  # 2 green
    ("#e87ba4", "#d55181"),  # 3 magenta
    ("#eda100", "#c98500"),  # 4 yellow
    ("#1baf7a", "#199e70"),  # 5 aqua
    ("#eb6834", "#d95926"),  # 6 orange
    ("#4a3aa7", "#9085e9"),  # 7 violet
    ("#e34948", "#e66767"),  # 8 red
]
# Secondary encoding (shape) so reaches stay distinguishable without color.
SHAPES = ["circle", "square", "triangle", "diamond", "circle", "square", "triangle", "diamond"]
GLYPH = {"circle": "●", "square": "▪", "triangle": "▲", "diamond": "◆"}


def fetch_reaches(gpkg: Path, reach_ids):
    """Return {reach_id: [[flow, ds_wse, bc], ...]} pulled from scenarios."""
    con = sqlite3.connect(str(gpkg))
    cur = con.cursor()
    # sanity-check the table/columns exist
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scenarios'")
    if not cur.fetchone():
        sys.exit(f"error: no 'scenarios' table found in {gpkg}")
    cols = {r[1] for r in cur.execute("PRAGMA table_info(scenarios)")}
    need = {"reach_id", "us_flow", "ds_wse", "boundary_condition"}
    missing = need - cols
    if missing:
        sys.exit(f"error: scenarios is missing columns: {sorted(missing)}")

    out = {}
    for rid in reach_ids:
        rows = cur.execute(
            "SELECT us_flow, ds_wse, boundary_condition FROM scenarios WHERE reach_id=? ORDER BY us_flow, ds_wse",
            (rid,),
        ).fetchall()
        if not rows:
            print(f"warning: reach {rid} has no rows in scenarios — skipping", file=sys.stderr)
            continue
        out[rid] = [[r[0], r[1], r[2]] for r in rows]
    con.close()
    return out


def build_html(series, title):
    """series: list of dicts {reach_id, label, points, light, dark, shape}."""
    # per-series CSS custom properties (light + dark)
    light_vars = "".join(f"    --s{i + 1}:{s['light']};\n" for i, s in enumerate(series))
    dark_vars = "".join(f"      --s{i + 1}:{s['dark']};\n" for i, s in enumerate(series))
    dark_vars2 = "".join(f"    --s{i + 1}:{s['dark']};\n" for i, s in enumerate(series))

    data_js = json.dumps(
        [
            {
                "reach_id": s["reach_id"],
                "role": s["label"],
                "slot": f"s{i + 1}",
                "shape": s["shape"],
                "points": s["points"],
            }
            for i, s in enumerate(series)
        ]
    )

    return (
        TEMPLATE.replace("/*LIGHT_VARS*/", light_vars.rstrip("\n"))
        .replace("/*DARK_VARS_A*/", dark_vars.rstrip("\n"))
        .replace("/*DARK_VARS_B*/", dark_vars2.rstrip("\n"))
        .replace("__TITLE__", _esc(title))
        .replace("__DATA__", data_js)
    )


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{
    color-scheme: light dark;
    --page:#f9f9f7; --surface:#fcfcfb;
    --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
/*LIGHT_VARS*/
  }
  @media (prefers-color-scheme: dark){
    :root:where(:not([data-theme="light"])){
      --page:#0d0d0d; --surface:#1a1a19;
      --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
      --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
/*DARK_VARS_A*/
    }
  }
  :root[data-theme="dark"]{
    --page:#0d0d0d; --surface:#1a1a19;
    --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
/*DARK_VARS_B*/
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--page);color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.45;}
  .wrap{max-width:1000px;margin:0 auto;padding:28px 20px 56px;}
  h1{font-size:1.4rem;margin:0 0 4px;font-weight:650;}
  .sub{color:var(--ink2);font-size:.92rem;margin:0 0 18px;max-width:70ch;}
  .card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
    padding:16px 16px 8px;box-shadow:0 1px 2px rgba(0,0,0,.04);}
  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:6px;}
  .chip{display:inline-flex;align-items:center;gap:8px;cursor:pointer;user-select:none;
    border:1px solid var(--border);background:transparent;border-radius:999px;
    padding:6px 12px 6px 10px;font-size:.86rem;color:var(--ink);transition:opacity .12s;}
  .chip .sw{width:22px;height:12px;flex:0 0 auto;}
  .chip[aria-pressed="false"]{opacity:.4;}
  .chip[aria-pressed="false"] .lab{text-decoration:line-through;}
  .ghost{border:1px solid var(--border);background:transparent;color:var(--ink2);
    border-radius:8px;padding:6px 12px;font-size:.84rem;cursor:pointer;}
  .ghost[aria-pressed="true"]{color:var(--ink);border-color:var(--axis);}
  figure{margin:0;}
  svg{display:block;width:100%;height:auto;overflow:visible;}
  .gridline{stroke:var(--grid);stroke-width:1;}
  .axisline{stroke:var(--axis);stroke-width:1;}
  .tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums;}
  .atitle{fill:var(--ink2);font-size:12px;font-weight:550;}
  .dlabel{font-size:11.5px;font-weight:650;}
  .band{opacity:.14;}
  .cline{fill:none;stroke-width:2;}
  .mk{stroke:var(--surface);stroke-width:1.2;}
  .cap{color:var(--muted);font-size:.78rem;padding:10px 2px 6px;}
  .tt{position:fixed;pointer-events:none;z-index:10;background:var(--surface);
    border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:.8rem;
    box-shadow:0 4px 14px rgba(0,0,0,.16);opacity:0;transition:opacity .08s;max-width:240px;}
  .tt b{font-size:.82rem;}
  .tt .row{display:flex;gap:8px;justify-content:space-between;color:var(--ink2);}
  .tt .row b{color:var(--ink);font-variant-numeric:tabular-nums;}
  .tblwrap{overflow-x:auto;margin-top:10px;display:none;}
  table{border-collapse:collapse;font-size:.82rem;width:100%;}
  th,td{text-align:right;padding:5px 10px;border-bottom:1px solid var(--grid);
    font-variant-numeric:tabular-nums;white-space:nowrap;}
  th:first-child,td:first-child{text-align:left;}
  thead th{color:var(--ink2);font-weight:600;border-bottom:1px solid var(--axis);}
  .rid{display:inline-flex;align-items:center;gap:7px;}
  .rid .sw{width:14px;height:10px;}
</style>
</head>
<body>
<div class="wrap">
  <h1>__TITLE__</h1>
  <p class="sub">Downstream water-surface elevation vs. discharge. The shaded band is each
  reach's flow envelope &mdash; the range of downstream WSEL spanned by all boundary conditions
  run at each flow; the solid line is the normal-depth rating curve; dots are the individual
  computed points. Click a reach to toggle it; the axes re-scale to what's shown.</p>

  <div class="card">
    <div class="controls" id="legend"></div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin:2px 0 8px;">
      <button class="ghost" id="pointsBtn" aria-pressed="true">Data points</button>
      <button class="ghost" id="tableBtn" aria-pressed="false">Table view</button>
    </div>
    <figure>
      <svg id="chart" viewBox="0 0 900 500" role="img"
           aria-label="Flow envelope chart of downstream WSEL versus discharge."></svg>
    </figure>
    <div class="cap" id="cap"></div>
    <div class="tblwrap" id="tblwrap"></div>
  </div>
</div>
<div class="tt" id="tt"></div>

<script>
const DATA = __DATA__;
DATA.forEach(d=>{ d.points = d.points.map(p=>({flow:p[0], wse:p[1], bc:p[2]})); });
DATA.forEach(d=>{
  const byFlow = new Map();
  d.points.forEach(p=>{
    if(!byFlow.has(p.flow)) byFlow.set(p.flow,{flow:p.flow,lo:Infinity,hi:-Infinity,nd:null});
    const g=byFlow.get(p.flow);
    g.lo=Math.min(g.lo,p.wse); g.hi=Math.max(g.hi,p.wse);
    if(p.bc==="nd") g.nd=p.wse;
  });
  d.env=[...byFlow.values()].sort((a,b)=>a.flow-b.flow);
});

const visible = new Set(DATA.map(d=>d.reach_id));
let showPoints = true, showTable = false;

const svg = document.getElementById('chart');
const NS = "http://www.w3.org/2000/svg";
const W=900,H=500, M={l:64,r:110,t:18,b:52};
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function el(tag,attrs){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);return e;}
function niceTicks(min,max,n){
  const span=max-min||1, raw=span/n, mag=Math.pow(10,Math.floor(Math.log10(raw)));
  const norm=raw/mag, step=(norm<1.5?1:norm<3?2:norm<7?5:10)*mag;
  const t=[]; for(let v=Math.ceil(min/step)*step; v<=max+1e-9; v+=step) t.push(+v.toFixed(6)); return t;
}
function markerPath(shape,cx,cy,r){
  if(shape==="square") return el("rect",{x:cx-r,y:cy-r,width:2*r,height:2*r,rx:1});
  if(shape==="triangle"){const h=r*1.25;return el("polygon",{points:`${cx},${cy-h} ${cx+h},${cy+h*0.85} ${cx-h},${cy+h*0.85}`});}
  if(shape==="diamond"){const h=r*1.3;return el("polygon",{points:`${cx},${cy-h} ${cx+h},${cy} ${cx},${cy+h} ${cx-h},${cy}`});}
  return el("circle",{cx,cy,r});
}

function render(){
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const shown = DATA.filter(d=>visible.has(d.reach_id));
  let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
  (shown.length?shown:DATA).forEach(d=>d.env.forEach(g=>{
    xmin=Math.min(xmin,g.flow); xmax=Math.max(xmax,g.flow);
    ymin=Math.min(ymin,g.lo);   ymax=Math.max(ymax,g.hi);
  }));
  const ypad=(ymax-ymin)*0.08||1; ymin-=ypad; ymax+=ypad;
  const xpad=(xmax-xmin)*0.03||1; const x0=Math.max(0,xmin-xpad), x1=xmax+xpad;
  const px=v=>M.l+(v-x0)/(x1-x0)*(W-M.l-M.r);
  const py=v=>H-M.b-(v-ymin)/(ymax-ymin)*(H-M.t-M.b);

  niceTicks(ymin,ymax,6).forEach(t=>{
    const y=py(t);
    svg.appendChild(el("line",{class:"gridline",x1:M.l,x2:W-M.r,y1:y,y2:y}));
    const tx=el("text",{class:"tick",x:M.l-9,y:y+4,"text-anchor":"end"});tx.textContent=t;svg.appendChild(tx);
  });
  niceTicks(x0,x1,7).forEach(t=>{
    const x=px(t);
    svg.appendChild(el("line",{class:"gridline",x1:x,x2:x,y1:M.t,y2:H-M.b}));
    const tx=el("text",{class:"tick",x:x,y:H-M.b+18,"text-anchor":"middle"});tx.textContent=t.toLocaleString();svg.appendChild(tx);
  });
  svg.appendChild(el("line",{class:"axisline",x1:M.l,x2:M.l,y1:M.t,y2:H-M.b}));
  svg.appendChild(el("line",{class:"axisline",x1:M.l,x2:W-M.r,y1:H-M.b,y2:H-M.b}));
  const xt=el("text",{class:"atitle",x:(M.l+W-M.r)/2,y:H-10,"text-anchor":"middle"});
  xt.textContent="Discharge  (cfs)";svg.appendChild(xt);
  const yt=el("text",{class:"atitle",x:16,y:(M.t+H-M.b)/2,"text-anchor":"middle",
    transform:`rotate(-90,16,${(M.t+H-M.b)/2})`});
  yt.textContent="Downstream WSEL  (ft)";svg.appendChild(yt);

  shown.forEach(d=>{
    const col=cssv('--'+d.slot);
    const up=d.env.map(g=>`${px(g.flow)},${py(g.hi)}`);
    const dn=d.env.slice().reverse().map(g=>`${px(g.flow)},${py(g.lo)}`);
    if(d.env.some(g=>g.hi>g.lo))
      svg.appendChild(el("polygon",{class:"band",points:up.concat(dn).join(" "),fill:col}));
    const nd=d.env.filter(g=>g.nd!=null);
    if(nd.length>1){
      const dpath=nd.map((g,i)=>(i?"L":"M")+px(g.flow)+" "+py(g.nd)).join(" ");
      svg.appendChild(el("path",{class:"cline",d:dpath,stroke:col}));
    }
    if(showPoints) d.points.forEach(p=>{
      const m=markerPath(d.shape,px(p.flow),py(p.wse), p.bc==="nd"?4.6:3.4);
      m.setAttribute("class","mk"); m.setAttribute("fill",col);
      m.setAttribute("fill-opacity", p.bc==="nd"?"1":"0.72");
      m.dataset.info=JSON.stringify({r:d.reach_id,role:d.role,flow:p.flow,wse:p.wse,bc:p.bc});
      svg.appendChild(m);
    });
    const last=d.env[d.env.length-1];
    const ly=py((last.hi+last.lo)/2);
    const t=el("text",{class:"dlabel",x:px(last.flow)+9,y:ly+4,fill:col});
    t.textContent=d.reach_id+" · "+d.role; svg.appendChild(t);
  });

  if(!shown.length){
    const t=el("text",{class:"tick",x:W/2,y:H/2,"text-anchor":"middle"});
    t.textContent="No reach selected"; svg.appendChild(t);
  }
  document.getElementById('cap').textContent =
    "Solid line = normal-depth rating curve · shaded band = known-WSEL envelope · larger dots = normal depth. "
    + (shown.length<DATA.length ? "Axes rescaled to the "+shown.length+" reach"+(shown.length===1?"":"es")+" shown." : "");
}

const tt=document.getElementById('tt');
svg.addEventListener('mousemove',ev=>{
  const pt=svg.getBoundingClientRect();
  const sx=(ev.clientX-pt.left)/pt.width*W, sy=(ev.clientY-pt.top)/pt.height*H;
  let best=null,bd=1e9;
  svg.querySelectorAll('.mk').forEach(m=>{
    const b=m.getBBox(), cx=b.x+b.width/2, cy=b.y+b.height/2;
    const dd=(cx-sx)**2+(cy-sy)**2;
    if(dd<bd){bd=dd;best=m;}
  });
  if(best && bd<600){
    const i=JSON.parse(best.dataset.info);
    tt.innerHTML=`<b>${i.r} · ${i.role}</b>
      <div class="row"><span>Discharge</span><b>${i.flow.toLocaleString()} cfs</b></div>
      <div class="row"><span>DS WSEL</span><b>${i.wse.toFixed(1)} ft</b></div>
      <div class="row"><span>Boundary</span><b>${i.bc==="nd"?"normal depth":"known WSEL"}</b></div>`;
    tt.style.opacity=1; tt.style.left=(ev.clientX+14)+'px'; tt.style.top=(ev.clientY+14)+'px';
    best.setAttribute('stroke-width','2.4');
  } else { tt.style.opacity=0; }
});
svg.addEventListener('mouseleave',()=>{tt.style.opacity=0;});

const legend=document.getElementById('legend');
const GLYPH={circle:"●",square:"▪",triangle:"▲",diamond:"◆"};
DATA.forEach(d=>{
  const b=document.createElement('button');
  b.className='chip'; b.setAttribute('aria-pressed','true');
  b.innerHTML=`<span class="sw" style="color:var(--${d.slot})">
    <svg width="22" height="12"><line x1="1" y1="6" x2="21" y2="6" stroke="currentColor" stroke-width="2.5"/></svg>
    </span><span class="lab">${d.reach_id} · ${d.role} ${GLYPH[d.shape]||""}</span>`;
  b.onclick=()=>{
    if(visible.has(d.reach_id)){visible.delete(d.reach_id);b.setAttribute('aria-pressed','false');}
    else{visible.add(d.reach_id);b.setAttribute('aria-pressed','true');}
    render(); buildTable();
  };
  legend.appendChild(b);
});
document.getElementById('pointsBtn').onclick=function(){
  showPoints=!showPoints; this.setAttribute('aria-pressed',showPoints); render();
};
document.getElementById('tableBtn').onclick=function(){
  showTable=!showTable; this.setAttribute('aria-pressed',showTable);
  document.getElementById('tblwrap').style.display=showTable?'block':'none'; buildTable();
};

function buildTable(){
  const wrap=document.getElementById('tblwrap'); if(!showTable){return;}
  const shown=DATA.filter(d=>visible.has(d.reach_id));
  let h='<table><thead><tr><th>Reach</th><th>Discharge (cfs)</th><th>Envelope lo (ft)</th>'
    +'<th>Envelope hi (ft)</th><th>Normal-depth (ft)</th></tr></thead><tbody>';
  shown.forEach(d=>d.env.forEach((g,i)=>{
    h+=`<tr><td>${i===0?`<span class="rid"><span class="sw" style="background:var(--${d.slot})"></span>${d.reach_id} · ${d.role}</span>`:''}</td>`
     +`<td>${g.flow.toLocaleString()}</td><td>${g.lo.toFixed(1)}</td><td>${g.hi.toFixed(1)}</td>`
     +`<td>${g.nd!=null?g.nd.toFixed(1):'—'}</td></tr>`;
  }));
  h+='</tbody></table>'; wrap.innerHTML=h;
}

render();
new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
</script>
</body>
</html>
"""


def parse_reach_arg(arg):
    """'6211748' or '6211748:headwater' -> (int_id, label)."""
    if ":" in arg:
        rid, label = arg.split(":", 1)
        return int(rid), label.strip()
    return int(arg), str(arg)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate a flow-envelope HTML chart from a ripple1d GeoPackage.")
    ap.add_argument("gpkg", type=Path, help="path to the .gpkg file")
    ap.add_argument("reaches", nargs="+", help="reach ids, in draw order. Use ID or ID:label (e.g. 6211748:headwater).")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("flow_envelopes.html"),
        help="output HTML path (default: flow_envelopes.html)",
    )
    ap.add_argument("--title", default="Flow Envelopes by Reach", help="chart title / <title> text")
    ap.add_argument("--open", action="store_true", help="open the result in the default browser when done")
    args = ap.parse_args(argv)

    if not args.gpkg.exists():
        sys.exit(f"error: file not found: {args.gpkg}")

    parsed = [parse_reach_arg(a) for a in args.reaches]
    if len(parsed) > len(PALETTE):
        sys.exit(
            f"error: max {len(PALETTE)} reaches supported (the validated categorical palette has {len(PALETTE)} slots)."
        )

    data = fetch_reaches(args.gpkg, [rid for rid, _ in parsed])
    if not data:
        sys.exit("error: none of the requested reaches were found in scenarios.")

    series = []
    for i, (rid, label) in enumerate(parsed):
        if rid not in data:
            continue
        light, dark = PALETTE[i]
        series.append(
            {
                "reach_id": rid,
                "label": label,
                "points": data[rid],
                "light": light,
                "dark": dark,
                "shape": SHAPES[i],
            }
        )

    html = build_html(series, args.title)
    args.out.write_text(html, encoding="utf-8")
    total = sum(len(s["points"]) for s in series)
    print(f"wrote {args.out}  ({len(series)} reaches, {total} points)")
    if args.open:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
