export interface IdentityField {
  name: string;
  type?: string;
}

export interface IdentityCategory {
  type: "category";
  name?: string;
  children?: IdentityField[];
}

export interface IdentityUser {
  type: "user";
  name?: string;
  collection?: string;
  identifiers?: Record<string, unknown>;
  children?: IdentityCategory[];
  stats?: { fields?: number };
}

export interface SimUserNode {
  id: string;
  type: "user";
  name?: string;
  collection?: string;
  data: unknown;
  color: string;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface SimRootNode {
  id: string;
  type: "root";
  name?: string;
  x: number;
  y: number;
  fx: number;
  fy: number;
}

export type SimNode = SimRootNode | SimUserNode;
