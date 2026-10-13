import React, { useEffect, useRef, useState } from "react";
import { BG } from "./identity/identityConstants";
import { hashColor, catStyleDetails, parseField } from "./identity/identityUtils";
import type { IdentityUser, IdentityCategory, IdentityField } from "./identity/identityTypes";

// ─── MultiDonut ─────────────────────────────────────────────────────────────
export interface UserDetailsMultiDonutProps {
  cats: IdentityCategory[];
  size?: number;
}

function UserDetailsMultiDonut({ cats, size = 72 }: UserDetailsMultiDonutProps) {
  const cx = size / 2, cy = size / 2;
  const r = size * 0.36, sw = size * 0.14;
  const circ = 2 * Math.PI * r;
  const total = cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.length || 0), 0);
  if (!total) return null;

  let acc = 0;
  const slices = cats.map((cat: IdentityCategory) => {
    const st = catStyleDetails(cat.name);
    const count = cat.children?.length || 0;
    const pct = count / total;
    const dashLen = Math.max(0, pct * circ - circ * 0.01);
    const s = { color: st.color, dashLen, dashOffset: acc };
    acc += pct * circ;
    return s;
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(15,23,42,0.08)" strokeWidth={sw} />
      {slices.map((s: { color: string; dashLen: number; dashOffset: number }, i: number) => (
        <circle key={i} cx={cx} cy={cy} r={r} fill="none"
          stroke={s.color} strokeWidth={sw}
          strokeDasharray={`${s.dashLen} ${circ - s.dashLen}`}
          strokeDashoffset={-s.dashOffset + circ * 0.25}
          strokeLinecap="butt" opacity={0.9}
          style={{ filter: `drop-shadow(0 0 2px ${s.color}66)` }}
        />
      ))}
      <circle cx={cx} cy={cy} r={r - sw / 2 - 1} fill={BG} />
      <text x={cx} y={cy - 4} textAnchor="middle" fill="#0f172a" fontSize={size * 0.18} fontWeight="800" fontFamily="Syne,sans-serif">{cats.length}</text>
      <text x={cx} y={cy + 10} textAnchor="middle" fill="rgba(15,23,42,0.5)" fontSize={size * 0.12} fontFamily="IBM Plex Mono,monospace">cats</text>
    </svg>
  );
}

// ─── CatPie ─────────────────────────────────────────────────────────────────
export interface UserDetailsCatPieProps {
  filled: number;
  total: number;
  color: string;
  size?: number;
}

function UserDetailsCatPie({ filled, total, color, size = 58 }: UserDetailsCatPieProps) {
  const cx = size / 2, cy = size / 2;
  const r = size * 0.36, sw = size * 0.15;
  const circ = 2 * Math.PI * r;
  const pct = total > 0 ? filled / total : 0;
  const dash = Math.max(0, pct * circ);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(15,23,42,0.1)" strokeWidth={sw} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={sw}
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ * 0.25}
        strokeLinecap="round" opacity={0.88}
        style={{ filter: `drop-shadow(0 0 3px ${color}66)` }}
      />
      <circle cx={cx} cy={cy} r={r - sw / 2 - 1} fill={BG} />
      <text x={cx} y={cy + 4} textAnchor="middle" fill="#0f172a" fontSize={size * 0.2} fontWeight="800" fontFamily="IBM Plex Mono,monospace">
        {Math.round(pct * 100)}
        <tspan fontSize={size * 0.12} fill="rgba(15,23,42,0.55)">%</tspan>
      </text>
    </svg>
  );
}

// ─── UserRootCard ────────────────────────────────────────────────────────────
export interface UserDetailsUserRootCardProps {
  user: IdentityUser;
  cats: IdentityCategory[];
  color: string;
  cardRef: React.RefObject<HTMLDivElement | null> | ((el: HTMLDivElement | null) => void);
}

function UserDetailsUserRootCard({ user, cats, color, cardRef }: UserDetailsUserRootCardProps) {
  const totalFields = cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.length || 0), 0);
  const initials = (user.name || "").split(" ").map((w: string) => w[0]).slice(0, 2).join("").toUpperCase() || "?";

  return (
    <div ref={cardRef} style={{ width: 310, background: "rgba(255,255,255,0.98)", border: `1.5px solid ${color}45`, borderRadius: 16, overflow: "hidden", boxShadow: `0 0 40px ${color}18, 0 12px 40px rgba(15,23,42,0.08)` }}>
      <div style={{ height: 3, background: `linear-gradient(90deg, ${color}, ${color}44)` }} />
      <div style={{ padding: "1.05rem 1.15rem .95rem", background: `linear-gradient(135deg, ${color}12 0%, transparent 100%)`, borderBottom: "1px solid rgba(15,23,42,0.08)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: ".75rem", marginBottom: ".6rem" }}>
          <div style={{ width: 46, height: 46, borderRadius: 12, flexShrink: 0, background: `${color}22`, border: `2px solid ${color}55`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: ".88rem", fontWeight: 800, color, letterSpacing: ".03em" }}>{initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "1rem", fontWeight: 700, color: "#0f172a", lineHeight: 1.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</div>
            {user.collection && (
              <span style={{ display: "inline-block", marginTop: ".28rem", fontSize: ".62rem", background: "rgba(13,148,136,0.12)", border: "1px solid rgba(13,148,136,0.3)", borderRadius: 4, padding: ".07rem .38rem", color: "#0f766e", fontFamily: "'IBM Plex Mono',monospace" }}>{user.collection}</span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: ".28rem" }}>
          {Object.entries(user.identifiers || {}).map(([k, v]) => (
            <span key={k} style={{ fontSize: ".6rem", background: "rgba(15,23,42,0.06)", border: "1px solid rgba(15,23,42,0.1)", borderRadius: 4, padding: ".07rem .35rem", color: "rgba(15,23,42,0.65)", fontFamily: "'IBM Plex Mono',monospace" }}>{k}: {String(v)}</span>
          ))}
        </div>
      </div>
      <div style={{ padding: ".75rem 1.15rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "flex", gap: "1.1rem", marginBottom: ".4rem" }}>
            {[{ label: "CAT", val: cats.length, clr: "#0d9488" }, { label: "FLD", val: totalFields, clr: "#38bdf8" }].map(({ label, val, clr }) => (
              <div key={label} style={{ display: "flex", alignItems: "baseline", gap: ".35rem" }}>
                <span style={{ fontSize: ".6rem", color: "rgba(15,23,42,0.5)", fontFamily: "'IBM Plex Mono',monospace", letterSpacing: ".06em" }}>{label}</span>
                <span style={{ fontSize: "1.05rem", fontWeight: 800, color: clr, fontFamily: "'IBM Plex Mono',monospace", lineHeight: 1 }}>{val}</span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: "1.1rem" }}>
            {[
              { label: "FILL", val: cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.filter((f: IdentityField) => { const { val } = parseField(f.name); return val && val.trim(); }).length || 0), 0), clr: "#059669" },
              { label: "EMPT", val: totalFields - cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.filter((f: IdentityField) => { const { val } = parseField(f.name); return val && val.trim(); }).length || 0), 0), clr: "rgba(15,23,42,0.45)" },
            ].map(({ label, val, clr }) => (
              <div key={label} style={{ display: "flex", alignItems: "baseline", gap: ".35rem" }}>
                <span style={{ fontSize: ".6rem", color: "rgba(15,23,42,0.5)", fontFamily: "'IBM Plex Mono',monospace", letterSpacing: ".06em" }}>{label}</span>
                <span style={{ fontSize: "1.05rem", fontWeight: 800, color: clr, fontFamily: "'IBM Plex Mono',monospace", lineHeight: 1 }}>{val}</span>
              </div>
            ))}
          </div>
        </div>
        <UserDetailsMultiDonut cats={cats} size={72} />
      </div>
    </div>
  );
}

// ─── CatCard ─────────────────────────────────────────────────────────────────
export interface UserDetailsCatCardProps {
  cat: IdentityCategory;
  totalFields: number;
  cardRef: React.RefObject<HTMLDivElement | null> | ((el: HTMLDivElement | null) => void);
}

function UserDetailsCatCard({ cat, totalFields, cardRef }: UserDetailsCatCardProps) {
  const st = catStyleDetails(cat.name);
  const fields = cat.children ?? [];
  const filledFields = fields.filter((f: IdentityField) => {
    const { val } = parseField(f.name);
    return val && val.trim() !== "";
  });
  const emptyFields = fields.length - filledFields.length;
  const pct = totalFields > 0 ? fields.length / totalFields : 0;
  const catName = (cat.name || "").replace(/^[^\w]+/, "").trim();

  return (
    <div ref={cardRef} style={{ width: 270, background: "rgba(255,255,255,0.98)", border: `1px solid ${st.color}40`, borderRadius: 14, overflow: "hidden", boxShadow: "0 6px 28px rgba(15,23,42,0.08)", flexShrink: 0 }}>
      <div style={{ height: 2.5, background: `linear-gradient(90deg, ${st.color}dd, ${st.color}22)` }} />
      <div style={{ padding: ".65rem .9rem .6rem", background: `linear-gradient(90deg, ${st.color}18 0%, transparent 100%)`, borderBottom: `1px solid ${st.color}25`, display: "flex", alignItems: "center", gap: ".5rem" }}>
        <span style={{ fontSize: ".9rem", flexShrink: 0 }}>{st.icon}</span>
        <span style={{ fontWeight: 700, fontSize: ".84rem", color: "#0f172a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{catName}</span>
        <span style={{ fontSize: ".62rem", color: st.color, background: `${st.color}22`, padding: ".05rem .32rem", borderRadius: 4, flexShrink: 0, fontFamily: "'IBM Plex Mono',monospace", fontWeight: 700 }}>{fields.length}</span>
      </div>
      <div style={{ padding: ".6rem .9rem .55rem", borderBottom: "1px solid rgba(15,23,42,0.06)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "flex", gap: ".85rem", marginBottom: ".35rem" }}>
            {[{ label: "FLD", val: fields.length, clr: st.color }, { label: "FILL", val: filledFields.length, clr: "#059669" }].map(({ label, val, clr }) => (
              <div key={label} style={{ display: "flex", alignItems: "baseline", gap: ".3rem" }}>
                <span style={{ fontSize: ".57rem", color: "rgba(15,23,42,0.5)", fontFamily: "'IBM Plex Mono',monospace", letterSpacing: ".05em" }}>{label}</span>
                <span style={{ fontSize: ".95rem", fontWeight: 800, color: clr, fontFamily: "'IBM Plex Mono',monospace", lineHeight: 1 }}>{val}</span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: ".85rem" }}>
            {[{ label: "EMPT", val: emptyFields, clr: "rgba(15,23,42,0.45)" }, { label: "PROF", val: `${(pct * 100).toFixed(0)}%`, clr: "#0d9488" }].map(({ label, val, clr }) => (
              <div key={label} style={{ display: "flex", alignItems: "baseline", gap: ".3rem" }}>
                <span style={{ fontSize: ".57rem", color: "rgba(15,23,42,0.5)", fontFamily: "'IBM Plex Mono',monospace", letterSpacing: ".05em" }}>{label}</span>
                <span style={{ fontSize: ".95rem", fontWeight: 800, color: clr, fontFamily: "'IBM Plex Mono',monospace", lineHeight: 1 }}>{val}</span>
              </div>
            ))}
          </div>
        </div>
        <UserDetailsCatPie filled={filledFields.length} total={fields.length} color={st.color} size={58} />
      </div>
      <div style={{ maxHeight: 260, overflowY: "auto", overflowX: "hidden" }}>
        {fields.length === 0 ? (
          <div style={{ padding: "1rem .9rem", color: "rgba(15,23,42,0.45)", fontSize: ".72rem", fontFamily: "'IBM Plex Mono',monospace", textAlign: "center", fontStyle: "italic" }}>No fields</div>
        ) : fields.map((f: IdentityField, i: number) => {
          const { key, val } = parseField(f.name);
          const hasVal = val && val.trim() !== "";
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: ".55rem", padding: ".42rem .9rem", borderBottom: i < fields.length - 1 ? "1px solid rgba(15,23,42,0.06)" : "none", background: i % 2 === 0 ? "rgba(15,23,42,0.02)" : "transparent" }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0, background: hasVal ? st.color : "rgba(15,23,42,0.15)", boxShadow: hasVal ? `0 0 5px ${st.color}88` : "none" }} />
              <div style={{ display: "flex", minWidth: 0, gap: 5 }}>
                <div style={{ fontSize: ".78rem", fontWeight: 600, lineHeight: 1.15, color: hasVal ? "rgba(15,23,42,0.9)" : "rgba(15,23,42,0.45)", fontFamily: "'IBM Plex Mono',monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{key} -</div>
                <div style={{ fontSize: ".78rem", lineHeight: 1.15, marginTop: ".06rem", color: hasVal ? st.color + "dd" : "rgba(15,23,42,0.35)", fontFamily: "'IBM Plex Mono',monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontStyle: hasVal ? "normal" : "italic" }}>{val || "—"}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── OrgTreeLayout (main export) ─────────────────────────────────────────────
export interface UserDetailsOrgTreeLayoutProps {
  user: IdentityUser;
  cats: IdentityCategory[];
}

export function UserDetailsOrgTreeLayout({ user, cats }: UserDetailsOrgTreeLayoutProps) {
  const color = hashColor((user.name || "") + (user.collection || ""));
  const totalFields = cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.length || 0), 0);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const catRefs = useRef<(HTMLDivElement | null)[]>([]);

  const [svgPaths, setSvgPaths] = useState<string[]>([]);
  const [svgW, setSvgW] = useState(0);
  const [svgH, setSvgH] = useState(0);

  const calcLines = () => {
    const inner = innerRef.current;
    const root = rootRef.current;
    if (!inner || !root || catRefs.current.length === 0) return;

    const iRect = inner.getBoundingClientRect();
    const rRect = root.getBoundingClientRect();
    const rx = rRect.left - iRect.left + rRect.width / 2;
    const ry = rRect.bottom - iRect.top;

    const centres = catRefs.current
      .map(ref => {
        if (!ref) return null;
        const rect = ref.getBoundingClientRect();
        return { x: rect.left - iRect.left + rect.width / 2, y: rect.top - iRect.top };
      })
      .filter((c): c is { x: number; y: number } => c != null);

    if (centres.length === 0) return;

    const first = centres[0];
    const last = centres[centres.length - 1];
    const midY = ry + (first.y - ry) * 0.48;
    const paths: string[] = [];
    paths.push(`M ${rx} ${ry} V ${midY}`);
    if (centres.length > 1) paths.push(`M ${first.x} ${midY} H ${last.x}`);
    centres.forEach(c => { paths.push(`M ${c.x} ${midY} V ${c.y}`); });

    setSvgPaths(paths);
    setSvgW(inner.scrollWidth);
    setSvgH(inner.scrollHeight);
  };

  useEffect(() => {
    const id = requestAnimationFrame(() => { calcLines(); setTimeout(calcLines, 250); });
    const onResize = () => requestAnimationFrame(calcLines);
    window.addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(id); window.removeEventListener("resize", onResize); };
  }, [cats.length]);

  return (
    <div ref={wrapperRef} style={{ flex: 1, overflow: "auto" }}>
      <div ref={innerRef} style={{ position: "relative", padding: "60px 90px 90px", minWidth: "max-content", minHeight: "100%", boxSizing: "border-box" }}>
        <svg style={{ position: "absolute", top: 0, left: 0, width: svgW || "100%", height: svgH || "100%", pointerEvents: "none", overflow: "visible" }}>
          <defs>
            <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto">
              <polygon points="0 0, 6 2, 0 4" fill="rgba(15,23,42,0.25)" />
            </marker>
          </defs>
          {svgPaths.map((d, i) => (
            <path key={i} d={d} stroke="rgba(15,23,42,0.2)" strokeWidth={1.5} fill="none" strokeLinejoin="round" />
          ))}
          {catRefs.current.map((ref, i) => {
            if (!ref) return null;
            const inner = innerRef.current;
            if (!inner) return null;
            const iRect = inner.getBoundingClientRect();
            const cRect = ref.getBoundingClientRect();
            const cx = cRect.left - iRect.left + cRect.width / 2;
            const cy = cRect.top - iRect.top;
            return (
              <circle key={`dot-${i}`} cx={cx} cy={cy} r={3} fill={catStyleDetails(cats[i]?.name).color} opacity={0.7} style={{ filter: `drop-shadow(0 0 3px ${catStyleDetails(cats[i]?.name).color})` }} />
            );
          })}
        </svg>
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 72 }}>
          <UserDetailsUserRootCard user={user} cats={cats} color={color} cardRef={rootRef} />
        </div>
        <div style={{ display: "flex", gap: 22, justifyContent: cats.length <= 4 ? "center" : "flex-start", alignItems: "flex-start", flexWrap: "nowrap" }}>
          {cats.map((cat: IdentityCategory, i: number) => (
            <UserDetailsCatCard key={i} cat={cat} totalFields={totalFields} cardRef={(el: HTMLDivElement | null) => { catRefs.current[i] = el; }} />
          ))}
        </div>
      </div>
    </div>
  );
}
