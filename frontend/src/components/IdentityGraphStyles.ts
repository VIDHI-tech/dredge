import React from "react";
import { BG, SIDEBAR_W } from "./identity/identityConstants";

/* Light theme: Dredge logo–inspired (teal, light blue, light grey) */
export const IdentityGraphStyles = {
  root: {
    position: "relative" as const, width: "100%", height: "100%", minHeight: "580px",
    background: BG,
    display: "flex", flexDirection: "column" as const, overflow: "hidden",
  },
  topBar: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 1.1rem", height: "52px", flexShrink: 0,
    background: "rgba(255,255,255,0.8)",
    borderBottom: "1px solid rgba(15,23,42,0.08)",
    gap: "1rem",
  },
  topLeft: { display: "flex", alignItems: "center", gap: ".9rem" },
  graphLabel: { fontSize: "1rem", fontWeight: 800, letterSpacing: ".15em", color: "#0d9488" },
  pill: { fontSize: ".72rem", color: "rgba(15,23,42,0.55)", fontFamily: "'IBM Plex Mono',monospace" },
  simBadge: {
    display: "flex", alignItems: "center", gap: ".4rem",
    fontSize: ".7rem", color: "rgba(15,23,42,0.6)", fontFamily: "'IBM Plex Mono',monospace",
  },
  dot: { width: 6, height: 6, borderRadius: "50%", background: "#059669", display: "inline-block" },
  topRight: { display: "flex", alignItems: "center", gap: ".6rem" },
  search: {
    background: "rgba(255,255,255,0.9)", border: "1px solid rgba(15,23,42,0.12)",
    borderRadius: "7px", color: "#0f172a", padding: ".38rem .7rem", fontSize: ".78rem",
    fontFamily: "'IBM Plex Mono',monospace", width: "200px", transition: "border-color .2s",
  },
  fitBtn: {
    background: "rgba(255,255,255,0.9)", border: "1px solid rgba(15,23,42,0.12)",
    borderRadius: "7px", color: "#0f172a",
    padding: ".38rem .7rem", fontSize: ".78rem", cursor: "pointer",
    transition: "all .2s",
  },
  canvasWrap: { flex: 1, position: "relative" as const, overflow: "hidden" },
  loadMore: {
    position: "absolute" as const, bottom: "1.25rem", left: "50%", transform: "translateX(-50%)",
    background: "rgba(13,148,136,0.15)", border: "1px solid rgba(13,148,136,0.4)",
    borderRadius: "8px", color: "#0f766e", padding: ".45rem 1.4rem",
    fontSize: ".78rem", cursor: "pointer", fontFamily: "'IBM Plex Mono',monospace",
    backdropFilter: "blur(8px)", whiteSpace: "nowrap" as const,
  },
  emptyOverlay: {
    position: "absolute" as const, top: "50%", left: "50%", transform: "translate(-50%,-50%)",
    textAlign: "center" as const, color: "rgba(15,23,42,0.45)",
    fontSize: ".9rem", fontFamily: "'IBM Plex Mono',monospace", pointerEvents: "none" as const,
  },
  legend: {
    position: "absolute" as const, bottom: "1.25rem", right: "1.25rem",
    display: "flex", alignItems: "center", gap: ".3rem",
    fontSize: ".7rem", color: "rgba(15,23,42,0.55)",
    fontFamily: "'IBM Plex Mono',monospace",
    background: "rgba(255,255,255,0.95)", backdropFilter: "blur(8px)",
    padding: ".4rem .8rem", borderRadius: "6px", border: "1px solid rgba(15,23,42,0.1)",
  },
  legendDot: { width: 8, height: 8, borderRadius: "50%", display: "inline-block" },
  sidebar: {
    position: "absolute" as const, top: 0, right: 0,
    width: `${SIDEBAR_W}px`, height: "100%",
    background: "rgba(255,255,255,0.98)",
    borderLeft: "1px solid rgba(15,23,42,0.08)",
    backdropFilter: "blur(24px)",
    display: "flex", flexDirection: "column" as const,
    zIndex: 100, overflow: "hidden",
  },
  sbHeader: {
    display: "flex", alignItems: "flex-start", gap: ".8rem",
    padding: "1rem 1.05rem .85rem",
    borderBottom: "1px solid rgba(15,23,42,0.08)", flexShrink: 0,
  },
  avatar: (col: string): React.CSSProperties => ({
    width: 42, height: 42, borderRadius: "10px", flexShrink: 0,
    background: `${col}22`, border: `2px solid ${col}55`,
    display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: ".8rem", fontWeight: 800, color: col, letterSpacing: ".04em",
  }),
  uName: {
    fontSize: ".92rem", fontWeight: 700, color: "#0f172a",
    marginBottom: ".32rem", lineHeight: 1.3, wordBreak: "break-word" as const,
  },
  metaRow: { display: "flex", flexWrap: "wrap" as const, gap: ".28rem" },
  idBadge: {
    fontSize: ".62rem", background: "rgba(15,23,42,0.06)",
    border: "1px solid rgba(15,23,42,0.12)",
    borderRadius: "4px", padding: ".09rem .38rem",
    color: "#334155", fontFamily: "'IBM Plex Mono',monospace",
  },
  collBadge: {
    fontSize: ".62rem", background: "rgba(13,148,136,0.12)",
    border: "1px solid rgba(13,148,136,0.3)",
    borderRadius: "4px", padding: ".09rem .38rem",
    color: "#0f766e", fontFamily: "'IBM Plex Mono',monospace",
  },
  closeBtn: {
    background: "none", border: "none", color: "#475569",
    fontSize: "1rem", cursor: "pointer", padding: ".3rem .35rem",
    lineHeight: 1, flexShrink: 0, marginLeft: "auto", transition: "color .15s",
  },
  dashRow: {
    display: "flex",
    borderBottom: "1px solid rgba(15,23,42,0.12)",
    flexShrink: 0, minHeight: 0,
  },
  dashLeft: {
    display: "flex", alignItems: "center", gap: ".55rem",
    padding: ".8rem .85rem",
    borderRight: "1px solid rgba(15,23,42,0.12)",
    flexShrink: 0,
  },
  donutLegend: { display: "flex", flexDirection: "column" as const, minWidth: 72, maxWidth: 100 },
  dashRight: { flex: 1, display: "flex", flexDirection: "column" as const },
  statCell: {
    display: "flex", alignItems: "center", gap: ".45rem",
    padding: ".42rem .85rem", flex: 1,
  },
  statN: {
    fontSize: "1.05rem", fontWeight: 800,
    fontFamily: "'IBM Plex Mono',monospace", lineHeight: 1,
  },
  statL: {
    fontSize: ".57rem", color: "#475569",
    letterSpacing: ".07em", textTransform: "uppercase" as const,
  },
  stackedWrap: {
    padding: ".55rem 1.05rem .6rem",
    borderBottom: "1px solid rgba(15,23,42,0.12)", flexShrink: 0,
  },
  microLabel: {
    fontSize: ".6rem", fontWeight: 700, letterSpacing: ".1em",
    textTransform: "uppercase" as const, color: "#475569",
  },
  sbBody: { flex: 1, overflowY: "auto" as const, padding: ".95rem 1.05rem" },
  secLabel: {
    fontSize: ".62rem", fontWeight: 700, letterSpacing: ".1em",
    textTransform: "uppercase" as const, color: "#475569", marginBottom: ".7rem",
  },
  empty: {
    color: "#64748b", fontSize: ".85rem",
    textAlign: "center" as const, padding: "2rem 0", fontFamily: "'IBM Plex Mono',monospace",
  },
  backBtn: {
    background: "none", border: "none", color: "#475569",
    fontSize: ".76rem", cursor: "pointer", padding: "0 0 .8rem 0", display: "block",
    fontFamily: "'IBM Plex Mono',monospace", transition: "color .15s",
  },
};
