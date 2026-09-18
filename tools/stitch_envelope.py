#!/usr/bin/env python3
"""
Fully AI Generated

stitch_envelope.py — Visualize a reach *stitch point* from a ripple1d GeoPackage.

A stitch point is a junction where two reaches meet. The upstream reach's
DOWNSTREAM end and the downstream reach's UPSTREAM end are the *same physical
location*, so their flow-vs-WSEL rating envelopes should coincide. This chart
overlays the two so you can see the match — and quantifies the mismatch by
interpolating the two normal-depth curves onto their shared flow range.

You name the stitch point by the UPSTREAM reach whose downstream end it is; the
downstream neighbor is resolved from the `network` table (updated_to_id, else
nwm_to_id). Override with --ds-reach if needed.

The GPKG must have:
  * scenarios(reach_id, us_flow, us_wse, ds_wse, boundary_condition)
  * network(reach_id, nwm_to_id, updated_to_id)   [only for auto-resolve]

Usage
-----
    python stitch_envelope.py RIPPLE.gpkg 6211748
    python stitch_envelope.py RIPPLE.gpkg 6211748 --ds-reach 6212600 -o stitch.html --open

Standard library only.
"""

import argparse
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path

# Two-sided comparison palette: upstream side (blue) vs downstream side (orange).
# Both are validated dataviz categorical slots (1 and 6); distinct hues so the
# two overlapping envelopes stay readable. (light, dark)
US_COLOR = ("#2a78d6", "#3987e5")  # upstream reach, d/s end
DS_COLOR = ("#eb6834", "#d95926")  # downstream reach, u/s end


def table_cols(cur, table):
    return {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}


def resolve_ds_reach(cur, up_reach):
    """Downstream neighbor of up_reach from the network table."""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='network'")
    if not cur.fetchone():
        return None
    row = cur.execute("SELECT * FROM network WHERE reach_id=?", (up_reach,)).fetchone()
    if not row:
        return None
    d = dict(zip([c[0] for c in cur.description], row))
    return d.get("updated_to_id") or d.get("nwm_to_id")


def fetch_side(cur, reach, field):
    """Return [[flow, wse, bc], ...] for reach using field 'us_wse' or 'ds_wse'."""
    rows = cur.execute(
        f"SELECT us_flow, {field}, boundary_condition FROM scenarios WHERE reach_id=? ORDER BY us_flow, " + field,
        (reach,),
    ).fetchall()
    return [[r[0], r[1], r[2]] for r in rows]


def build_html(stitch, series, title):
    data_js = json.dumps(series)
    return (
        TEMPLATE.replace("__TITLE__", _esc(title))
        .replace("__US_L__", US_COLOR[0])
        .replace("__US_D__", US_COLOR[1])
        .replace("__DS_L__", DS_COLOR[0])
        .replace("__DS_D__", DS_COLOR[1])
        .replace("__STITCH__", _esc(stitch))
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
    --s1:__US_L__; --s2:__DS_L__;
  }
  @media (prefers-color-scheme: dark){
    :root:where(:not([data-theme="light"])){
      --page:#0d0d0d; --surface:#1a1a19;
      --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
      --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
      --s1:__US_D__; --s2:__DS_D__;
    }
  }
  :root[data-theme="dark"]{
    --page:#0d0d0d; --surface:#1a1a19;
    --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --s1:__US_D__; --s2:__DS_D__;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--page);color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.45;}
  .wrap{max-width:1000px;margin:0 auto;padding:28px 20px 56px;}
  h1{font-size:1.4rem;margin:0 0 4px;font-weight:650;}
  .sub{color:var(--ink2);font-size:.92rem;margin:0 0 16px;max-width:72ch;}
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
  .statbar{display:flex;gap:22px;flex-wrap:wrap;margin:4px 2px 2px;}
  .stat{display:flex;flex-direction:column;gap:1px;}
  .stat .v{font-size:1.05rem;font-weight:650;font-variant-numeric:tabular-nums;}
  .stat .k{font-size:.72rem;color:var(--muted);}
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
  <p class="sub">Stitch point <b>__STITCH__</b>. The two curves are the <em>same physical
  location</em> seen from each side of the junction: the upstream reach's downstream-end
  rating envelope and the downstream reach's upstream-end rating envelope. They should
  coincide &mdash; visible daylight between the bands is stitch mismatch. Shaded band = the
  WSEL range across all boundary conditions at each flow; solid line = each side's control
  curve (upstream reach: normal depth; downstream reach u/s end: <em>lowest elevation</em>);
  dots = computed points. Click a side to toggle it.</p>

  <div class="card">
    <div class="controls" id="legend"></div>
    <div class="statbar" id="statbar"></div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin:2px 0 8px;">
      <button class="ghost" id="pointsBtn" aria-pressed="true">Data points</button>
      <button class="ghost" id="tableBtn" aria-pressed="false">Table view</button>
    </div>
    <figure>
      <svg id="chart" viewBox="0 0 900 500" role="img"
           aria-label="Stitch-point rating envelopes from both sides of a reach junction."></svg>
    </figure>
    <div class="cap" id="cap"></div>
    <div class="tblwrap" id="tblwrap"></div>
  </div>
</div>
<div class="tt" id="tt"></div>

<script>
const DATA = __DATA__;   // [{reach_id, role, side, slot, shape, lineType, points:[[flow,wse,bc]]}]
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
  // control line: "min" = lowest elevation per flow (band bottom); "nd" = normal-depth curve
  d.linePts = (d.lineType==="min")
    ? d.env.map(g=>({flow:g.flow, wse:g.lo}))
    : d.env.filter(g=>g.nd!=null).map(g=>({flow:g.flow, wse:g.nd}));
});

const visible = new Set(DATA.map(d=>d.reach_id+"|"+d.side));
const key = d => d.reach_id+"|"+d.side;
let showPoints = true, showTable = false;

const svg = document.getElementById('chart');
const NS = "http://www.w3.org/2000/svg";
const W=900,H=500, M={l:64,r:120,t:18,b:52};
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function el(tag,attrs){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);return e;}
function niceTicks(min,max,n){
  const span=max-min||1, raw=span/n, mag=Math.pow(10,Math.floor(Math.log10(raw)));
  const norm=raw/mag, step=(norm<1.5?1:norm<3?2:norm<7?5:10)*mag;
  const t=[]; for(let v=Math.ceil(min/step)*step; v<=max+1e-9; v+=step) t.push(+v.toFixed(6)); return t;
}
function markerPath(shape,cx,cy,r){
  if(shape==="diamond"){const h=r*1.3;return el("polygon",{points:`${cx},${cy-h} ${cx+h},${cy} ${cx},${cy+h} ${cx-h},${cy}`});}
  return el("circle",{cx,cy,r});
}
// linear interpolation of an nd curve (sorted by flow) at flow f, or null if out of range
function interp(nd,f){
  if(nd.length<2) return null;
  if(f<nd[0].flow || f>nd[nd.length-1].flow) return null;
  for(let i=1;i<nd.length;i++){
    if(f<=nd[i].flow){
      const a=nd[i-1],b=nd[i]; const t=(f-a.flow)/((b.flow-a.flow)||1);
      return a.wse+t*(b.wse-a.wse);
    }
  }
  return nd[nd.length-1].wse;
}
// stitch mismatch: max & mean |ΔWSEL| between the two control lines over shared flow range
function mismatch(){
  if(DATA.length<2) return null;
  const A=DATA[0].linePts, B=DATA[1].linePts;
  if(A.length<2||B.length<2) return null;
  const lo=Math.max(A[0].flow,B[0].flow), hi=Math.min(A[A.length-1].flow,B[B.length-1].flow);
  if(hi<=lo) return null;
  const flows=[...new Set([...A,...B].map(p=>p.flow))].filter(f=>f>=lo&&f<=hi).sort((a,b)=>a-b);
  let mx=0,sum=0,n=0,mxAt=null;
  flows.forEach(f=>{
    const a=interp(A,f), b=interp(B,f);
    if(a!=null&&b!=null){const dd=Math.abs(a-b); if(dd>mx){mx=dd;mxAt=f;} sum+=dd; n++;}
  });
  return n? {max:mx,mean:sum/n,at:mxAt,lo,hi} : null;
}

function render(){
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const shown = DATA.filter(d=>visible.has(key(d)));
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
  yt.textContent="WSEL at junction  (ft)";svg.appendChild(yt);

  shown.forEach(d=>{
    const col=cssv('--'+d.slot);
    const up=d.env.map(g=>`${px(g.flow)},${py(g.hi)}`);
    const dn=d.env.slice().reverse().map(g=>`${px(g.flow)},${py(g.lo)}`);
    if(d.env.some(g=>g.hi>g.lo))
      svg.appendChild(el("polygon",{class:"band",points:up.concat(dn).join(" "),fill:col}));
    if(d.linePts.length>1){
      const dpath=d.linePts.map((g,i)=>(i?"L":"M")+px(g.flow)+" "+py(g.wse)).join(" ");
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
    const t=el("text",{class:"dlabel",x:px(last.flow)+9,y:py((last.hi+last.lo)/2)+4,fill:col});
    t.textContent=d.reach_id+" · "+d.role; svg.appendChild(t);
  });

  if(!shown.length){
    const t=el("text",{class:"tick",x:W/2,y:H/2,"text-anchor":"middle"});
    t.textContent="No side selected"; svg.appendChild(t);
  }
  // stats + caption
  const mm=mismatch(); const sb=document.getElementById('statbar'); sb.innerHTML='';
  if(mm){
    const mk=(v,k)=>`<div class="stat"><span class="v">${v}</span><span class="k">${k}</span></div>`;
    sb.innerHTML = mk(mm.max.toFixed(2)+" ft","Max WSEL mismatch")
      + mk(mm.mean.toFixed(2)+" ft","Mean WSEL mismatch")
      + mk(mm.lo.toLocaleString()+"–"+mm.hi.toLocaleString()+" cfs","Shared flow range");
  }
  document.getElementById('cap').textContent =
    "Shaded band = WSEL range across boundary conditions · solid line = each side's control curve "
    + "(upstream: normal depth; downstream u/s: lowest elevation) · larger dots = normal-depth boundary."
    + (mm? "  Mismatch = |ΔWSEL| between the two control lines, interpolated onto shared flows"
         + (mm.at!=null? " (worst near "+Math.round(mm.at).toLocaleString()+" cfs)." : "."):"");
}

const tt=document.getElementById('tt');
svg.addEventListener('mousemove',ev=>{
  const pt=svg.getBoundingClientRect();
  const sx=(ev.clientX-pt.left)/pt.width*W, sy=(ev.clientY-pt.top)/pt.height*H;
  let best=null,bd=1e9;
  svg.querySelectorAll('.mk').forEach(m=>{
    const b=m.getBBox(), cx=b.x+b.width/2, cy=b.y+b.height/2;
    const dd=(cx-sx)**2+(cy-sy)**2; if(dd<bd){bd=dd;best=m;}
  });
  if(best && bd<600){
    const i=JSON.parse(best.dataset.info);
    tt.innerHTML=`<b>${i.r} · ${i.role}</b>
      <div class="row"><span>Discharge</span><b>${i.flow.toLocaleString()} cfs</b></div>
      <div class="row"><span>WSEL</span><b>${i.wse.toFixed(1)} ft</b></div>
      <div class="row"><span>Boundary</span><b>${i.bc==="nd"?"normal depth":"known WSEL"}</b></div>`;
    tt.style.opacity=1; tt.style.left=(ev.clientX+14)+'px'; tt.style.top=(ev.clientY+14)+'px';
    best.setAttribute('stroke-width','2.4');
  } else { tt.style.opacity=0; }
});
svg.addEventListener('mouseleave',()=>{tt.style.opacity=0;});

const legend=document.getElementById('legend');
const GLYPH={circle:"●",diamond:"◆"};
DATA.forEach(d=>{
  const b=document.createElement('button');
  b.className='chip'; b.setAttribute('aria-pressed','true');
  b.innerHTML=`<span class="sw" style="color:var(--${d.slot})">
    <svg width="22" height="12"><line x1="1" y1="6" x2="21" y2="6" stroke="currentColor" stroke-width="2.5"/></svg>
    </span><span class="lab">${d.reach_id} · ${d.role} ${GLYPH[d.shape]||""}</span>`;
  b.onclick=()=>{
    const k=key(d);
    if(visible.has(k)){visible.delete(k);b.setAttribute('aria-pressed','false');}
    else{visible.add(k);b.setAttribute('aria-pressed','true');}
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
  const shown=DATA.filter(d=>visible.has(key(d)));
  let h='<table><thead><tr><th>Side</th><th>Discharge (cfs)</th><th>Envelope lo (ft)</th>'
    +'<th>Envelope hi (ft)</th><th>Control line (ft)</th></tr></thead><tbody>';
  shown.forEach(d=>d.env.forEach((g,i)=>{
    const lv = d.lineType==="min" ? g.lo.toFixed(1) : (g.nd!=null?g.nd.toFixed(1):'—');
    h+=`<tr><td>${i===0?`<span class="rid"><span class="sw" style="background:var(--${d.slot})"></span>${d.reach_id} · ${d.role}</span>`:''}</td>`
     +`<td>${g.flow.toLocaleString()}</td><td>${g.lo.toFixed(1)}</td><td>${g.hi.toFixed(1)}</td>`
     +`<td>${lv}</td></tr>`;
  }));
  h+='</tbody></table>'; wrap.innerHTML=h;
}

render();
new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
</script>
</body>
</html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Visualize a reach stitch point (both-sided rating envelopes).")
    ap.add_argument("gpkg", type=Path, help="path to the .gpkg file")
    ap.add_argument("up_reach", type=int, help="the UPSTREAM reach whose downstream end is the stitch point")
    ap.add_argument("--ds-reach", type=int, default=None, help="downstream reach id (overrides network auto-resolve)")
    ap.add_argument("--us-label", default="d/s end", help="label for the upstream reach's side (default: 'd/s end')")
    ap.add_argument("--ds-label", default="u/s end", help="label for the downstream reach's side (default: 'u/s end')")
    ap.add_argument("-o", "--out", type=Path, default=Path("stitch_envelope.html"))
    ap.add_argument("--title", default=None, help="chart title (auto if omitted)")
    ap.add_argument("--open", action="store_true", help="open result in browser")
    args = ap.parse_args(argv)

    if not args.gpkg.exists():
        sys.exit(f"error: file not found: {args.gpkg}")

    con = sqlite3.connect(str(args.gpkg))
    cur = con.cursor()
    if not cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scenarios'").fetchone():
        sys.exit(f"error: no 'scenarios' table in {args.gpkg}")
    need = {"reach_id", "us_flow", "us_wse", "ds_wse", "boundary_condition"}
    missing = need - table_cols(cur, "scenarios")
    if missing:
        sys.exit(f"error: scenarios missing columns: {sorted(missing)}")

    up = args.up_reach
    down = args.ds_reach or resolve_ds_reach(cur, up)
    if down is None:
        sys.exit(
            f"error: could not resolve the downstream reach for {up} from the "
            f"network table. Pass it explicitly with --ds-reach."
        )

    us_pts = fetch_side(cur, up, "ds_wse")  # upstream reach, downstream END
    ds_pts = fetch_side(cur, down, "us_wse")  # downstream reach, upstream END
    con.close()
    if not us_pts:
        sys.exit(f"error: upstream reach {up} has no rows in scenarios.")
    if not ds_pts:
        sys.exit(f"error: downstream reach {down} has no rows in scenarios. (Is it in this model? Try --ds-reach.)")

    series = [
        # upstream reach, d/s end: control line is the normal-depth curve
        {
            "reach_id": up,
            "role": args.us_label,
            "side": "ds",
            "slot": "s1",
            "shape": "circle",
            "lineType": "nd",
            "points": us_pts,
        },
        # downstream reach, u/s end: control line is its lowest elevation per flow
        {
            "reach_id": down,
            "role": args.ds_label,
            "side": "us",
            "slot": "s2",
            "shape": "diamond",
            "lineType": "min",
            "points": ds_pts,
        },
    ]
    stitch = f"{up} (d/s) ↔ {down} (u/s)"
    title = args.title or f"Stitch point — {stitch}"

    html = build_html(stitch, series, title)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out}  (stitch {up} d/s <-> {down} u/s; {len(us_pts)}+{len(ds_pts)} points)")
    if args.open:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
