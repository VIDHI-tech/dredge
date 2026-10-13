import { BG } from "./identity/identityConstants";
import { catStyleViz, parseField } from "./identity/identityUtils";
import { IdentityGraphStyles } from "./IdentityGraphStyles";
import type { IdentityCategory, IdentityField } from "./identity/identityTypes";

const S = IdentityGraphStyles;

// ─── DonutChart ─────────────────────────────────────────────────────────────
export interface IdentityDonutChartProps {
  cats: IdentityCategory[];
  size?: number;
}

export function IdentityDonutChart({ cats, size = 90 }: IdentityDonutChartProps) {
  const cx = size / 2, cy = size / 2;
  const r = size * 0.36, strokeW = size * 0.12;
  const circumference = 2 * Math.PI * r;
  const total = cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.length || 0), 0);
  if (!total) return null;

  let accum = 0;
  const slices = cats.map((cat: IdentityCategory) => {
    const st = catStyleViz(cat.name);
    const count = cat.children?.length || 0;
    const pct = count / total;
    const dashLen = Math.max(0, pct * circumference - circumference * 0.008);
    const s = { color: st.color, dashLen, dashOffset: accum, pct, count };
    accum += pct * circumference;
    return s;
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(15,23,42,0.1)" strokeWidth={strokeW} />
      {slices.map((s: { color: string; dashLen: number; dashOffset: number; pct: number; count: number }, i: number) => (
        <circle key={i} cx={cx} cy={cy} r={r} fill="none"
          stroke={s.color} strokeWidth={strokeW}
          strokeDasharray={`${s.dashLen} ${circumference - s.dashLen}`}
          strokeDashoffset={-(s.dashOffset) + circumference * 0.25}
          strokeLinecap="butt" opacity={0.9}
          style={{ filter: `drop-shadow(0 0 3px ${s.color}88)` }}
        />
      ))}
      <circle cx={cx} cy={cy} r={r - strokeW / 2 - 2} fill={BG} />
      <text x={cx} y={cy - 5} textAnchor="middle" fill="#0f172a"
        fontSize={size * 0.145} fontWeight="800" fontFamily="Syne,sans-serif">{cats.length}</text>
      <text x={cx} y={cy + 9} textAnchor="middle" fill="rgba(15,23,42,0.55)"
        fontSize={size * 0.1} fontFamily="IBM Plex Mono,monospace">cats</text>
    </svg>
  );
}

// ─── RingProgress ────────────────────────────────────────────────────────────
export interface IdentityRingProgressProps {
  pct: number;
  color: string;
  size?: number;
  strokeW?: number;
}

export function IdentityRingProgress({ pct, color, size = 38, strokeW = 3.5 }: IdentityRingProgressProps) {
  const cx = size / 2, cy = size / 2, r = (size - strokeW) / 2 - 1;
  const circ = 2 * Math.PI * r;
  const dash = Math.max(0, pct * circ);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(15,23,42,0.12)" strokeWidth={strokeW} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={strokeW}
        strokeDasharray={`${dash} ${circ - dash}`} strokeDashoffset={circ * 0.25}
        strokeLinecap="round" style={{ filter: `drop-shadow(0 0 2px ${color}88)` }} />
    </svg>
  );
}

// ─── StackedBar ─────────────────────────────────────────────────────────────
export interface IdentityStackedBarProps {
  cats: IdentityCategory[];
}

export function IdentityStackedBar({ cats }: IdentityStackedBarProps) {
  const total = cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.length || 0), 0);
  if (!total) return null;
  return (
    <div style={{ display: "flex", height: 5, borderRadius: 3, overflow: "hidden", gap: 1 }}>
      {cats.map((cat: IdentityCategory, i: number) => {
        const st = catStyleViz(cat.name);
        const pct = ((cat.children?.length || 0) / total) * 100;
        return (
          <div key={i} title={`${cat.name}: ${cat.children?.length || 0}`}
            style={{ width: `${pct}%`, background: st.color, opacity: 0.75, transition: "width .4s cubic-bezier(.4,0,.2,1)" }} />
        );
      })}
    </div>
  );
}

// ─── CatList ─────────────────────────────────────────────────────────────────
export interface IdentityCatListProps {
  cats: IdentityCategory[];
  onSel: (cat: IdentityCategory) => void;
  totalFields: number;
}

export function IdentityCatList({ cats, onSel, totalFields }: IdentityCatListProps) {
  if (!cats.length)
    return <div style={S.empty}>No categories for this user.</div>;

  return (
    <div style={{ animation: "fadeUp .25s ease" }}>
      <div style={S.secLabel}>{cats.length} Categories · {totalFields} fields</div>
      <div style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
        {cats.map((cat: IdentityCategory, i: number) => {
          const st = catStyleViz(cat.name);
          const fields = cat.children ?? [];
          const pct = totalFields > 0 ? fields.length / totalFields : 0;
          const preview = fields.slice(0, 3);
          return (
            <button
              key={i}
              className="cat-card"
              onClick={() => onSel(cat)}
              style={{
                background: `linear-gradient(120deg, ${st.bg} 0%, rgba(0,0,0,0.0) 100%)`,
                border: `1px solid ${st.color}25`,
                borderRadius: "12px",
                padding: ".8rem .95rem",
                cursor: "pointer",
                textAlign: "left",
                width: "100%",
                animation: `fadeUp .22s ease ${i * 50}ms both`,
                position: "relative",
                overflow: "hidden",
              }}
            >
              <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2.5, background: `linear-gradient(180deg,${st.color}dd,${st.color}22)` }} />
              <div style={{ display: "flex", alignItems: "center", gap: ".65rem", marginBottom: ".55rem" }}>
                <div style={{ position: "relative", width: 38, height: 38, flexShrink: 0 }}>
                  <IdentityRingProgress pct={pct} color={st.color} size={38} strokeW={3.5} />
                  <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1rem" }}>{st.icon}</div>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: ".4rem", marginBottom: ".2rem" }}>
                    <span style={{ fontSize: ".86rem", fontWeight: 700, color: "#0f172a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {(cat.name || "").replace(/^[^\w]+/, "").trim()}
                    </span>
                    <span style={{ fontSize: ".63rem", fontWeight: 700, color: st.color, background: `${st.color}20`, padding: ".06rem .32rem", borderRadius: "4px", fontFamily: "'IBM Plex Mono',monospace", flexShrink: 0 }}>{fields.length}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: ".4rem" }}>
                    <div style={{ flex: 1, height: 2, background: "rgba(15,23,42,0.1)", borderRadius: 1 }}>
                      <div style={{ height: "100%", borderRadius: 1, background: st.color, opacity: 0.85, width: `${Math.min(100, pct * 100)}%`, transition: "width .5s cubic-bezier(.4,0,.2,1)" }} />
                    </div>
                    <span style={{ fontSize: ".59rem", color: "rgba(15,23,42,0.5)", fontFamily: "'IBM Plex Mono',monospace", flexShrink: 0 }}>{(pct * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </div>
              <div style={{ background: "rgba(15,23,42,0.06)", borderRadius: "7px", padding: ".38rem .5rem", display: "flex", flexDirection: "column", gap: ".15rem" }}>
                {preview.map((f: IdentityField, j: number) => {
                  const { key, val } = parseField(f.name);
                  return (
                    <div key={j} style={{ display: "flex", gap: ".45rem", alignItems: "baseline" }}>
                      <span style={{ fontSize: ".65rem", color: st.color, fontFamily: "'IBM Plex Mono',monospace", flexShrink: 0, width: "38%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{key}</span>
                      <span style={{ fontSize: ".65rem", color: "rgba(15,23,42,0.75)", fontFamily: "'IBM Plex Mono',monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{val || "—"}</span>
                    </div>
                  );
                })}
                {fields.length > 3 && (
                  <div style={{ fontSize: ".61rem", color: "rgba(15,23,42,0.5)", fontStyle: "italic", marginTop: ".08rem" }}>+{fields.length - 3} more → click to expand</div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── CatDetail ───────────────────────────────────────────────────────────────
export interface IdentityCatDetailProps {
  cat: IdentityCategory;
  onBack: () => void;
  totalFields: number;
}

export function IdentityCatDetail({ cat, onBack, totalFields }: IdentityCatDetailProps) {
  const st = catStyleViz(cat.name);
  const fields = cat.children ?? [];
  const pct = totalFields > 0 ? fields.length / totalFields : 0;
  const filledFields = fields.filter((f: IdentityField) => {
    const { val } = parseField(f.name);
    return val && val.trim() !== "";
  });
  const completeness = fields.length > 0 ? filledFields.length / fields.length : 0;

  return (
    <div style={{ animation: "slideIn .25s ease" }}>
      <button className="back-btn" style={S.backBtn} onClick={onBack}>← Back to categories</button>
      <div style={{ background: `linear-gradient(135deg, ${st.color}18 0%, rgba(0,0,0,0) 80%)`, border: `1px solid ${st.color}30`, borderRadius: "14px", padding: "1rem 1.05rem", marginBottom: ".9rem", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", right: -30, top: -30, width: 110, height: 110, background: `radial-gradient(circle, ${st.color}18 0%, transparent 70%)`, borderRadius: "50%", pointerEvents: "none" }} />
        <div style={{ display: "flex", alignItems: "center", gap: ".7rem", marginBottom: ".75rem" }}>
          <div style={{ position: "relative", width: 44, height: 44, flexShrink: 0 }}>
            <IdentityRingProgress pct={pct} color={st.color} size={44} strokeW={4} />
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.25rem" }}>{st.icon}</div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: ".95rem", fontWeight: 700, color: "#0f172a", fontFamily: "Syne,sans-serif" }}>{(cat.name || "").replace(/^[^\w]+/, "").trim()}</div>
            <div style={{ fontSize: ".66rem", color: "rgba(15,23,42,0.55)", fontFamily: "'IBM Plex Mono',monospace", marginTop: ".1rem" }}>{fields.length} fields · {(pct * 100).toFixed(0)}% of profile</div>
          </div>
          <span style={{ fontSize: ".7rem", color: st.color, fontFamily: "'IBM Plex Mono',monospace", background: `${st.color}20`, padding: ".1rem .45rem", borderRadius: "5px", border: `1px solid ${st.color}40` }}>{fields.length}</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: ".45rem", marginBottom: ".7rem" }}>
          {[
            { val: fields.length, label: "Fields", color: st.color },
            { val: filledFields.length, label: "Filled", color: "#059669" },
            { val: `${(completeness * 100).toFixed(0)}%`, label: "Complete", color: "#0d9488" },
          ].map(({ val, label, color }, i) => (
            <div key={i} style={{ background: "rgba(15,23,42,0.06)", borderRadius: "8px", padding: ".38rem .45rem", textAlign: "center" }}>
              <div style={{ fontSize: ".88rem", fontWeight: 800, color, fontFamily: "'IBM Plex Mono',monospace", lineHeight: 1 }}>{val}</div>
              <div style={{ fontSize: ".56rem", color: "rgba(15,23,42,0.5)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".12rem" }}>{label}</div>
            </div>
          ))}
        </div>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: ".28rem" }}>
            <span style={{ fontSize: ".59rem", color: "rgba(15,23,42,0.5)", fontFamily: "'IBM Plex Mono',monospace" }}>Completeness</span>
            <span style={{ fontSize: ".59rem", color: "#059669", fontFamily: "'IBM Plex Mono',monospace" }}>{(completeness * 100).toFixed(0)}%</span>
          </div>
          <div style={{ height: 4, background: "rgba(15,23,42,0.1)", borderRadius: 2 }}>
            <div style={{ height: "100%", borderRadius: 2, background: "linear-gradient(90deg, #059669, #0d9488)", width: `${completeness * 100}%`, transition: "width .6s cubic-bezier(.4,0,.2,1)" }} />
          </div>
        </div>
      </div>
      <div style={S.secLabel}>All Fields</div>
      <div style={{ borderRadius: "10px", overflow: "hidden", border: "1px solid rgba(15,23,42,0.12)" }}>
        {fields.map((f: IdentityField, i: number) => {
          const { key, val } = parseField(f.name);
          const hasVal = val && val.trim() !== "";
          return (
            <div key={i} className="frow" style={{ display: "flex", alignItems: "center", padding: ".5rem .8rem", background: i % 2 === 0 ? "rgba(15,23,42,0.02)" : "transparent", borderBottom: i < fields.length - 1 ? "1px solid rgba(15,23,42,0.08)" : "none", gap: ".6rem", animation: `fadeUp .16s ease ${Math.min(i, 16) * 18}ms both` }}>
              <div style={{ width: 4, height: 4, borderRadius: "50%", flexShrink: 0, background: hasVal ? st.color : "rgba(15,23,42,0.2)", boxShadow: hasVal ? `0 0 4px ${st.color}99` : "none" }} />
              <span style={{ flex: "0 0 38%", fontSize: ".68rem", color: hasVal ? st.color : "rgba(15,23,42,0.45)", fontFamily: "'IBM Plex Mono',monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{key}</span>
              <span style={{ flex: 1, fontSize: ".68rem", color: hasVal ? "#0f172a" : "rgba(15,23,42,0.4)", fontFamily: "'IBM Plex Mono',monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontStyle: hasVal ? "normal" : "italic" }}>{val || "—"}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
