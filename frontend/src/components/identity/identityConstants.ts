export const BG = "#f1f5f9";

export const USER_PALETTE = [
  "#0d9488", "#38bdf8", "#059669", "#0ea5e9",
  "#ec4899", "#06b6d4", "#8b5cf6", "#84cc16",
  "#6366f1", "#14b8a6", "#22d3ee", "#7c3aed",
];

export const CAT_MAP_VIZ = {
  location:  { color: "#0d9488", icon: "📍", bg: "rgba(13,148,136,0.12)" },
  financial: { color: "#0d9488", icon: "💰", bg: "rgba(13,148,136,0.12)" },
  political: { color: "#8b5cf6", icon: "🏛️", bg: "rgba(139,92,246,0.12)" },
  employer:  { color: "#dc2626", icon: "🏢", bg: "rgba(220,38,38,0.12)" },
  office:    { color: "#059669", icon: "🗃️", bg: "rgba(5,150,105,0.12)" },
  other:     { color: "#6366f1", icon: "📋", bg: "rgba(99,102,241,0.12)" },
} as const;

export const CAT_MAP_DETAILS = {
  location:  { color: "#0d9488", icon: "📍" },
  financial: { color: "#0d9488", icon: "💰" },
  political: { color: "#8b5cf6", icon: "🏛️" },
  employer:  { color: "#dc2626", icon: "🏢" },
  office:    { color: "#059669", icon: "🗃️" },
  other:     { color: "#6366f1", icon: "📋" },
} as const;

export const PAGE_SIZE = 200;
export const USER_R = 22;
export const ROOT_R = 34;
export const LINK_DIST = 140;
export const SIDEBAR_W = 460;
