export type ViewMode = 'schema' | 'sunburst' | 'usertree';

export interface SunburstNodeData {
  name?: string;
  value?: number;
  children?: unknown[];
  full_value?: string;
}

export interface NodeInsight {
  entity_type: string;
  title: string;
  summary: string;
  properties: { label: string; value: string }[];
  related_entities: string[];
}

export interface DetailState {
  open: boolean;
  title: string;
  loading: boolean;
  type: 'table' | 'concept' | 'row';
  rows: unknown[];
  columns: string[];
  equivalentFields: string[];
  total: number;
  conceptFields: { name: string; valCount: number; totalFreq: number }[];
  rowData: unknown;
  history: (() => void)[];
  insight: NodeInsight | null;
  insightLoading: boolean;
  /** The field name that triggered this table view — used for column highlight & search. */
  activeField?: string;
}

export const SUNBURST_COLORS = ['#0d9488', '#38bdf8', '#059669', '#0ea5e9', '#ec4899', '#06b6d4', '#8b5cf6', '#14b8a6', '#6366f1', '#7c3aed'];
