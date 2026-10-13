import { useEffect, useRef, useState, useMemo } from "react";
import * as React from "react";
import * as d3 from "d3";
import type { SimNode, SimRootNode, SimUserNode, IdentityUser, IdentityCategory } from "./identity/identityTypes";
import { PAGE_SIZE, USER_R, ROOT_R, LINK_DIST, BG } from "./identity/identityConstants";
import { hashColor, hexBright } from "./identity/identityUtils";
import { IdentityUserSidebar } from "./IdentityUserSidebar";
import { IdentityGraphStyles } from "./IdentityGraphStyles";

const S = IdentityGraphStyles;

// ─────────────────────────── main component ───────────────────────────────────

export default function UserIdentityGraph({ userTreeData, onUserClick, searchQ: searchQProp, setSearchQ: _setSearchQProp, setPage: setPageProp, page: pageProp, fitViewRef }: {
  userTreeData?: { tree?: { name?: string; children?: IdentityUser[] } };
  onUserClick?: (user: IdentityUser) => void;
  searchQ?: string;
  setSearchQ?: (v: string) => void;
  setPage?: (v: number | ((p: number) => number)) => void;
  page?: number;
  fitViewRef?: React.MutableRefObject<(() => void) | null>;
}) {

  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const simRef       = useRef<d3.Simulation<SimNode, d3.SimulationLinkDatum<SimNode>> | null>(null);
  const nodesRef     = useRef<SimNode[]>([]);
  const linksRef     = useRef<d3.SimulationLinkDatum<SimNode>[]>([]);
  const qtreeRef     = useRef<d3.Quadtree<SimNode> | null>(null);
  const tRef         = useRef(d3.zoomIdentity);
  const zoomRef      = useRef<d3.ZoomBehavior<HTMLCanvasElement, unknown> | null>(null);
  const rafRef       = useRef<number | null>(null);
  const selRef       = useRef<string | null>(null);
  const hovRef       = useRef<string | null>(null);

  const [dims, setDims]                 = useState({ w: 900, h: 620 });
  const [selectedUser, setSelectedUser] = useState<IdentityUser | null>(null);
  const [selCategory,  setSelCategory]  = useState<IdentityCategory | null>(null);
  const [hovId,        setHovId]        = useState<string | null>(null);
  const [searchQInternal, _setSearchQInternal] = useState("");
  const [pageInternal, setPageInternal] = useState(0);
  const [_simPct, setSimPct] = useState(0);

  const searchQ = searchQProp ?? searchQInternal;
  const setPage = setPageProp ?? setPageInternal;
  const page = pageProp ?? pageInternal;

  selRef.current = selectedUser ? `user-${selectedUser.name}-${selectedUser.collection}` : null;
  hovRef.current = hovId;

  const allUsers = useMemo(
    () => userTreeData?.tree?.children?.filter((c: IdentityUser) => c.type === "user") ?? [],
    [userTreeData]
  );
  const rootName   = userTreeData?.tree?.name || "Root";

  const filtered = useMemo(() => {
    const q = searchQ.toLowerCase().trim();
    if (!q) return allUsers;
    return allUsers.filter(u =>
      u.name?.toLowerCase().includes(q) ||
      u.collection?.toLowerCase().includes(q) ||
      JSON.stringify(u.identifiers || {}).toLowerCase().includes(q)
    );
  }, [allUsers, searchQ]);

  const visible = useMemo(
    () => filtered.slice(0, (page + 1) * PAGE_SIZE),
    [filtered, page]
  );

  // ── resize observer ──
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      setDims({ w: Math.floor(width), h: Math.floor(height) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // ── d3 zoom ──
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const zoom = d3.zoom<HTMLCanvasElement, unknown>().scaleExtent([0.04, 5])
      .on("zoom", (e: d3.D3ZoomEvent<HTMLCanvasElement, unknown>) => { tRef.current = e.transform; schedDraw(); });
    d3.select(canvas).call(zoom);
    zoomRef.current = zoom;
    return () => { d3.select(canvas).on(".zoom", null); };
  }, []);

  // ── force simulation ──
  useEffect(() => {
    if (!userTreeData) return;
    const { w, h } = dims;
    const prevPos: Record<string, { x: number; y: number }> = {};
    for (const n of nodesRef.current) {
      if ("id" in n) prevPos[n.id] = { x: (n as SimNode).x ?? 0, y: (n as SimNode).y ?? 0 };
    }

    const root: SimRootNode = { id:"__root__", type:"root", name:rootName, x:w/2, y:h/2, fx:w/2, fy:h/2 };
    const userNodes: SimUserNode[] = visible.map(u => {
      const id = `user-${u.name ?? ""}-${u.collection ?? ""}`;
      const p  = prevPos[id];
      return {
        id, type:"user" as const, name:u.name, collection:u.collection, stats:u.stats, data:u,
        color: hashColor((u.name ?? "") + (u.collection ?? "")),
        x: p?.x ?? w/2 + (Math.random()-.5)*400,
        y: p?.y ?? h/2 + (Math.random()-.5)*400,
      };
    });

    const nodes: SimNode[] = [root, ...userNodes];
    const links = userNodes.map(n => ({ source: "__root__" as const, target: n.id }));
    nodesRef.current = nodes;
    linksRef.current = links;

    if (simRef.current) simRef.current.stop();
    const sim = d3.forceSimulation<SimNode>(nodes)
      .force("link", d3.forceLink<SimNode, d3.SimulationLinkDatum<SimNode>>(links).id((d: d3.SimulationNodeDatum) => (d as SimNode).id).distance(LINK_DIST).strength(0.35))
      .force("charge", d3.forceManyBody().strength(-500).distanceMax(600))
      .force("collide", d3.forceCollide(USER_R + 8).strength(0.85))
      .force("center", d3.forceCenter(w/2, h/2).strength(0.04))
      .alphaDecay(0.025)
      .on("tick", () => { setSimPct(p => Math.min(99, p+1)); rebuildQTree(); schedDraw(); })
      .on("end",  () => { setSimPct(100); rebuildQTree(); schedDraw(); });
    simRef.current = sim;
    setSimPct(0);
    return () => { sim.stop(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, dims, rootName]);

  function rebuildQTree() {
    qtreeRef.current = d3.quadtree<SimNode>().x(d => d.x ?? 0).y(d => d.y ?? 0).addAll(nodesRef.current);
  }

  function schedDraw() {
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => { rafRef.current = null; draw(); });
  }

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width, H = canvas.height;
    const t = tRef.current;
    const nodes = nodesRef.current, links = linksRef.current;
    const selId = selRef.current, hovIdCur = hovRef.current;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H);

    // dot grid (light theme: subtle dark dots)
    ctx.save();
    const gSz = 40*t.k, ox = ((t.x%gSz)+gSz)%gSz, oy = ((t.y%gSz)+gSz)%gSz;
    ctx.fillStyle = "rgba(15,23,42,0.06)";
    for (let x=ox-gSz; x<W+gSz; x+=gSz)
      for (let y=oy-gSz; y<H+gSz; y+=gSz) {
        ctx.beginPath(); ctx.arc(x,y,.8,0,Math.PI*2); ctx.fill();
      }
    ctx.restore();

    ctx.save();
    ctx.translate(t.x,t.y); ctx.scale(t.k,t.k);
    const vx1=-t.x/t.k-120, vy1=-t.y/t.k-120, vx2=vx1+W/t.k+240, vy2=vy1+H/t.k+240;

    for (const lk of links) {
      const s=lk.source as SimNode, e=lk.target as SimNode;
      if (!s?.x||!e?.x) continue;
      if (s.x<vx1&&e.x<vx1) continue;
      if (s.x>vx2&&e.x>vx2) continue;
      const sel=e.id===selId, hov=e.id===hovIdCur;
      const sx = s.x ?? 0, sy = s.y ?? 0, ex = e.x ?? 0, ey = e.y ?? 0;
      ctx.beginPath(); ctx.moveTo(sx,sy); ctx.lineTo(ex,ey);
      ctx.strokeStyle = sel?"rgba(13,148,136,0.75)":hov?"rgba(15,23,42,0.45)":"rgba(15,23,42,0.28)";
      ctx.lineWidth = sel?2:1; ctx.stroke();
    }

    for (const n of nodes) {
      if (n.x == null) continue;
      const r = n.type==="root"?ROOT_R:USER_R;
      if (n.x+r<vx1||n.x-r>vx2||(n.y ?? 0)+r<vy1||(n.y ?? 0)-r>vy2) continue;
      n.type==="root" ? drawRoot(ctx,n as SimRootNode,t.k) : drawUser(ctx,n as SimUserNode,n.id===selId,n.id===hovIdCur,t.k);
    }
    ctx.restore();
  }

  /* Root: one distinct color (indigo) so it stands out from user nodes (teal/sky/etc) */
  const ROOT_COLOR = "#FF0000";
  function drawRoot(ctx: CanvasRenderingContext2D, n: SimRootNode, k: number) {
    const r = ROOT_R;
    const g = ctx.createRadialGradient(n.x,n.y,r,n.x,n.y,r*3.2);
    g.addColorStop(0,"rgba(99,102,241,0.22)"); g.addColorStop(1,"rgba(99,102,241,0)");
    ctx.beginPath(); ctx.arc(n.x,n.y,r*3.2,0,Math.PI*2); ctx.fillStyle=g; ctx.fill();
    const f = ctx.createRadialGradient(n.x-r*.3,n.y-r*.3,2,n.x,n.y,r);
    f.addColorStop(0,"#a5b4fc"); f.addColorStop(1,ROOT_COLOR);
    ctx.beginPath(); ctx.arc(n.x,n.y,r,0,Math.PI*2); ctx.fillStyle=f; ctx.fill();
    ctx.strokeStyle="rgba(99,102,241,0.75)"; ctx.lineWidth=2/k; ctx.stroke();
    ctx.fillStyle="#0f172a";
    ctx.font=`bold ${Math.max(7,Math.min(10,r*.3))}px Syne,sans-serif`;
    ctx.textAlign="center"; ctx.textBaseline="middle";
    ctx.fillText(n.name?.slice(0,10)||"ROOT",n.x,n.y);
  }

  function drawUser(ctx: CanvasRenderingContext2D, n: SimUserNode, isSel: boolean, isHov: boolean, k: number) {
    const r=USER_R, col=n.color;
    const nx = n.x ?? 0, ny = n.y ?? 0;
    if (isSel||isHov) {
      const g=ctx.createRadialGradient(nx,ny,r*.5,nx,ny,r*2.6);
      g.addColorStop(0,col+"55"); g.addColorStop(1,col+"00");
      ctx.beginPath(); ctx.arc(nx,ny,r*2.6,0,Math.PI*2); ctx.fillStyle=g; ctx.fill();
    }
    const f=ctx.createRadialGradient(nx-r*.35,ny-r*.35,2,nx,ny,r);
    f.addColorStop(0,hexBright(col,60)); f.addColorStop(1,hexBright(col,-35));
    ctx.beginPath(); ctx.arc(nx,ny,r,0,Math.PI*2); ctx.fillStyle=f; ctx.fill();
    ctx.strokeStyle=isSel?"#0f172a":isHov?col+"dd":col+"88";
    ctx.lineWidth=isSel?2.5/k:isHov?1.8/k:1.2/k; ctx.stroke();
    const init=(n.name||"").split(" ").map((w: string)=>w[0]).slice(0,2).join("").toUpperCase();
    const fs=Math.max(6,Math.min(9,r*.42));
    ctx.fillStyle="#0f172a";
    ctx.font=`bold ${fs}px Syne,sans-serif`;
    ctx.textAlign="center"; ctx.textBaseline="middle";
    ctx.fillText(init,nx,ny-1);
    if (k>0.45) {
      const label=(n.name||"").split(" ")[0].slice(0,11);
      ctx.fillStyle="#0f172a";
      ctx.font=`${Math.max(6,fs-1)}px 'IBM Plex Mono',monospace`;
      ctx.fillText(label,nx,ny+r+9);
    }
  }

  function nodeAt(px: number, py: number): SimNode | null {
    const t=tRef.current;
    const wx=(px-t.x)/t.k, wy=(py-t.y)/t.k;
    const qt=qtreeRef.current;
    if (!qt) return null;
    const margin=USER_R+6;
    let best: SimNode | null=null, bestD=Infinity;
    qt.visit((node: d3.QuadtreeInternalNode<SimNode> | d3.QuadtreeLeaf<SimNode>, x1: number, y1: number, x2: number, y2: number) => {
      if (x1>wx+margin||x2<wx-margin||y1>wy+margin||y2<wy-margin) return true;
      if (!node.length) {
        const d=(node as d3.QuadtreeLeaf<SimNode>).data;
        if (d) {
          const dx=(d.x ?? 0)-wx, dy=(d.y ?? 0)-wy, dist=Math.sqrt(dx*dx+dy*dy);
          const nr=d.type==="root"?ROOT_R:USER_R;
          if (dist<nr+4&&dist<bestD) { best=d; bestD=dist; }
        }
      }
    });
    return best;
  }

  useEffect(() => {
    const canvas=canvasRef.current; if (!canvas) return;
    let lastHov: string | null=null;
    const onMove = (e: Event) => {
      const ev = e as MouseEvent;
      const rect=canvas.getBoundingClientRect();
      const n=nodeAt(ev.clientX-rect.left,ev.clientY-rect.top);
      const id=n?.type==="user"?n.id:null;
      if (id!==lastHov) {
        lastHov=id; hovRef.current=id; setHovId(id);
        canvas.style.cursor=id?"pointer":"grab"; schedDraw();
      }
    };
    const onClick = (e: Event) => {
      const ev = e as MouseEvent;
      const rect=canvas.getBoundingClientRect();
      const n=nodeAt(ev.clientX-rect.left,ev.clientY-rect.top);
      if (n?.type==="user") { setSelectedUser(n.data as IdentityUser); setSelCategory(null); onUserClick?.(n.data as IdentityUser); }
    };
    canvas.addEventListener("mousemove",onMove);
    canvas.addEventListener("click",onClick);
    return () => { canvas.removeEventListener("mousemove",onMove); canvas.removeEventListener("click",onClick); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const canvas=canvasRef.current; if (!canvas) return;
    let dragN: SimUserNode | null=null, dragged=false;
    const onDown = (e: Event) => {
      const ev = e as MouseEvent;
      const rect=canvas.getBoundingClientRect();
      const n=nodeAt(ev.clientX-rect.left,ev.clientY-rect.top);
      if (n?.type==="user") { dragN=n; dragged=false; ev.stopPropagation(); }
    };
    const onMoveDrag=(e: MouseEvent) => {
      if (!dragN) return; dragged=true;
      const rect=canvas.getBoundingClientRect(), t=tRef.current;
      dragN.fx=(e.clientX-rect.left-t.x)/t.k;
      dragN.fy=(e.clientY-rect.top-t.y)/t.k;
      simRef.current?.alpha(0.3).restart();
    };
    const onUp=() => {
      if (dragN&&dragged) { dragN.fx=null; dragN.fy=null; simRef.current?.alpha(0.2).restart(); }
      dragN=null; dragged=false;
    };
    canvas.addEventListener("mousedown",onDown);
    window.addEventListener("mousemove",onMoveDrag);
    window.addEventListener("mouseup",onUp);
    return () => {
      canvas.removeEventListener("mousedown",onDown);
      window.removeEventListener("mousemove",onMoveDrag);
      window.removeEventListener("mouseup",onUp);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { schedDraw(); }, [selectedUser, hovId]);

  const fitView = () => {
    if (!zoomRef.current||!canvasRef.current) return;
    d3.select(canvasRef.current).transition().duration(700).call(zoomRef.current.transform, d3.zoomIdentity);
  };

  useEffect(() => {
    if (fitViewRef) {
      fitViewRef.current = fitView;
      return () => { fitViewRef.current = null; };
    }
  });

  const canvasH = Math.max(200, dims.h);

  return (
    <div style={S.root}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=IBM+Plex+Mono:wght@300;400;500&display=swap');
        @keyframes slideIn { from{opacity:0;transform:translateX(28px)} to{opacity:1;transform:translateX(0)} }
        @keyframes fadeUp  { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
        @keyframes pulse2  { 0%,100%{opacity:.5;transform:scale(1)} 50%{opacity:1;transform:scale(1.1)} }
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:rgba(15,23,42,0.2);border-radius:2px}
        .cat-card{transition:all .2s cubic-bezier(.4,0,.2,1)!important}
        .cat-card:hover{transform:translateY(-2px)!important;box-shadow:0 8px 24px rgba(15,23,42,0.12)!important;filter:brightness(0.98)!important}
        .fitbtn:hover{background:rgba(13,148,136,0.12)!important;color:#0f766e!important}
        .srch:focus{border-color:rgba(13,148,136,0.5)!important;outline:none}
        .close-btn:hover{color:#0f172a!important}
        .back-btn:hover{color:#0f172a!important}
        .frow:hover{background:rgba(15,23,42,0.04)!important;transition:background .12s}
        .see-tree-btn:hover{background:rgba(13,148,136,0.2)!important;border-color:rgba(13,148,136,0.5)!important;color:#0f766e!important;transform:translateY(-1px)!important;}
      `}</style>

      {/* canvas area */}
      <div ref={containerRef} style={S.canvasWrap}>
        <canvas ref={canvasRef} width={dims.w} height={canvasH}
          style={{ display:"block", width:"100%", height:"100%" }} />

        {visible.length < filtered.length && (
          <button style={S.loadMore} onClick={() => setPage(p => p+1)}>
            ＋ Load {Math.min(PAGE_SIZE, filtered.length-visible.length).toLocaleString()} more
            <span style={{opacity:.5,fontSize:".8em"}}> · {visible.length}/{filtered.length}</span>
          </button>
        )}

        {filtered.length===0 && searchQ && (
          <div style={S.emptyOverlay}>
            <div style={{fontSize:"2rem",marginBottom:".5rem"}}>🔍</div>
            <div>No users match "{searchQ}"</div>
          </div>
        )}

        <div style={S.legend}>
          <span style={{...S.legendDot,background:"#6366f1"}}/> Root
          <span style={{...S.legendDot,background:"#38bdf8",marginLeft:".75rem"}}/> User node
          <span style={{opacity:.4,fontSize:".7rem",marginLeft:".5rem"}}>drag · scroll to zoom</span>
        </div>
      </div>

      {/* sidebar */}
      <IdentityUserSidebar
        user={selectedUser}
        selCategory={selCategory}
        onSelCategory={setSelCategory}
        onClose={() => { setSelectedUser(null); setSelCategory(null); }}
        onClearCat={() => setSelCategory(null)}
      />
    </div>
  );
}
