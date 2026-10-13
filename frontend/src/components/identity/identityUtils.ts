import { USER_PALETTE, CAT_MAP_VIZ, CAT_MAP_DETAILS } from "./identityConstants";

export function hashColor(str: string): string {
  let h = 0;
  for (const c of (str || "")) h = (h * 31 + c.charCodeAt(0)) | 0;
  return USER_PALETTE[Math.abs(h) % USER_PALETTE.length];
}

export function catStyleViz(rawName: string | undefined): { color: string; icon: string; key: string; bg?: string } {
  const k = rawName?.toLowerCase().replace(/[^a-z]/g, "");
  for (const [key, val] of Object.entries(CAT_MAP_VIZ)) if (k?.includes(key)) return { ...val, key };
  return { ...CAT_MAP_VIZ.other, key: "other" };
}

export function catStyleDetails(rawName: string | undefined): { color: string; icon: string; key: string } {
  const k = rawName?.toLowerCase().replace(/[^a-z]/g, "");
  for (const [key, val] of Object.entries(CAT_MAP_DETAILS)) if (k?.includes(key)) return { ...val, key };
  return { ...CAT_MAP_DETAILS.other, key: "other" };
}

export function parseField(raw: string | undefined): { key: string; val: string } {
  const i = raw?.indexOf(": ");
  if (i != null && i > 0) return { key: raw!.slice(0, i).trim(), val: raw!.slice(i + 2).trim() };
  return { key: raw || "", val: "" };
}

export function hexBright(hex: string, amount: number): string {
  const n = parseInt((hex || "#888").replace("#", ""), 16);
  const r = Math.min(255, Math.max(0, ((n >> 16) & 255) + amount));
  const g = Math.min(255, Math.max(0, ((n >> 8) & 255) + amount));
  const b = Math.min(255, Math.max(0, (n & 255) + amount));
  return `rgb(${r},${g},${b})`;
}
