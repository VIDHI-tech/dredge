import { hashColor, catStyleViz } from "./identity/identityUtils";
import { IdentityDonutChart, IdentityStackedBar, IdentityCatList, IdentityCatDetail } from "./IdentitySidebarChartsAndLists";
import { IdentityGraphStyles } from "./IdentityGraphStyles";
import type { IdentityUser, IdentityCategory } from "./identity/identityTypes";

const S = IdentityGraphStyles;

export interface IdentityUserSidebarProps {
  user: IdentityUser | null;
  selCategory: IdentityCategory | null;
  onSelCategory: (cat: IdentityCategory | null) => void;
  onClose: () => void;
  onClearCat: () => void;
}

export function IdentityUserSidebar({ user, selCategory, onSelCategory, onClose, onClearCat }: IdentityUserSidebarProps) {
  const open = !!user;
  const color = user ? hashColor((user.name || "") + (user.collection || "")) : "#0d9488";
  const cats = user?.children?.filter((c: IdentityCategory) => c.type === "category") ?? [];
  const totalFields = cats.reduce((a: number, c: IdentityCategory) => a + (c.children?.length || 0), 0);

  return (
    <div style={{ ...S.sidebar, transform: open ? "translateX(0)" : "translateX(100%)", transition: "transform .38s cubic-bezier(.4,0,.2,1)" }}>
      {user && (
        <>
          <div style={{ ...S.sbHeader, borderLeft: `3px solid ${color}` }}>
            <div style={S.avatar(color)}>{(user.name || "").split(" ").map((w: string) => w[0]).slice(0, 2).join("").toUpperCase() || "?"}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={S.uName}>{user.name}</div>
              <div style={S.metaRow}>
                {Object.entries(user.identifiers || {}).map(([k, v]) => (
                  <span key={k} style={S.idBadge}>{k}: {String(v)}</span>
                ))}
                {user.collection && <span style={S.collBadge}>{user.collection}</span>}
              </div>
            </div>
            <button className="close-btn" style={S.closeBtn} onClick={onClose}>✕</button>
          </div>
          <div style={S.dashRow}>
            <div style={S.dashLeft}>
              <IdentityDonutChart cats={cats} size={84} />
              <div style={S.donutLegend}>
                {cats.slice(0, 4).map((cat: IdentityCategory, i: number) => {
                  const st = catStyleViz(cat.name);
                  const count = cat.children?.length || 0;
                  const pct = totalFields > 0 ? (count / totalFields * 100).toFixed(0) : 0;
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: ".32rem", marginBottom: ".22rem" }}>
                      <div style={{ width: 5, height: 5, borderRadius: "50%", background: st.color, flexShrink: 0 }} />
                      <span style={{ fontSize: ".61rem", color: "#475569", fontFamily: "'IBM Plex Mono',monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(cat.name || "").replace(/^[^\w]+/, "").trim().slice(0, 12)}</span>
                      <span style={{ fontSize: ".59rem", color: "#64748b", fontFamily: "'IBM Plex Mono',monospace", flexShrink: 0 }}>{pct}%</span>
                    </div>
                  );
                })}
                {cats.length > 4 && <div style={{ fontSize: ".58rem", color: "#64748b", marginTop: ".1rem" }}>+{cats.length - 4} more</div>}
              </div>
            </div>
            <div style={S.dashRight}>
              {[
                { n: cats.length, l: "Categories", icon: "🗂", clr: "#0d9488" },
                { n: totalFields, l: "Fields", icon: "📊", clr: "#38bdf8" },
                { n: user.stats?.fields ?? totalFields, l: "Data pts", icon: "⚡", clr: "#059669" },
              ].map(({ n, l, icon, clr }, i) => (
                <div key={i} style={{ ...S.statCell, borderTop: i > 0 ? "1px solid rgba(15,23,42,0.06)" : "none" }}>
                  <span style={{ fontSize: ".85rem" }}>{icon}</span>
                  <div>
                    <div style={{ ...S.statN, color: clr }}>{typeof n === "number" ? n.toLocaleString() : n}</div>
                    <div style={S.statL}>{l}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div style={S.stackedWrap}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: ".38rem" }}>
              <span style={S.microLabel}>Field Distribution</span>
              <span style={{ ...S.microLabel, opacity: 0.45 }}>{totalFields} total</span>
            </div>
            <IdentityStackedBar cats={cats} />
            <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap", marginTop: ".45rem" }}>
              {cats.map((cat: IdentityCategory, i: number) => {
                const st = catStyleViz(cat.name);
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: ".25rem" }}>
                    <div style={{ width: 5, height: 5, borderRadius: "50%", background: st.color }} />
                    <span style={{ fontSize: ".58rem", color: "#475569", fontFamily: "'IBM Plex Mono',monospace" }}>{(cat.name || "").replace(/^[^\w]+/, "").trim().slice(0, 10)}</span>
                  </div>
                );
              })}
            </div>
          </div>
          <div style={S.sbBody}>
            <button
              className="see-tree-btn"
              onClick={() => {
                try { sessionStorage.setItem("uidg_user_detail", JSON.stringify(user)); } catch (e) {}
                window.open("/dashboard/details");
              }}
              style={{ width: "100%", padding: ".58rem 1rem", marginBottom: ".85rem", background: "rgba(139,92,246,0.12)", border: "1px solid rgba(139,92,246,0.32)", borderRadius: "9px", color: "#c084fc", cursor: "pointer", fontSize: ".78rem", fontWeight: 700, letterSpacing: ".06em", display: "flex", alignItems: "center", justifyContent: "center", gap: ".45rem", transition: "all .2s cubic-bezier(.4,0,.2,1)", boxShadow: "0 2px 12px rgba(139,92,246,0.1)" }}
            >
              <span style={{ fontSize: ".9rem" }}>🌳</span> See Full Tree
            </button>
            {selCategory ? <IdentityCatDetail cat={selCategory} onBack={onClearCat} totalFields={totalFields} /> : <IdentityCatList cats={cats} onSel={onSelCategory} totalFields={totalFields} />}
          </div>
        </>
      )}
    </div>
  );
}
