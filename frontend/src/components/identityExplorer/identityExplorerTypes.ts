export interface ExplorerUser {
  build_id: string;
  user_key: string;
  display_name: string;
  sort_name: string;
  identifiers: Record<string, string>;
  record_count: number;
  collection_count: number;
  preview?: { collections?: string[] };
}

export interface ValueNodeAttribute {
  field_path: string;
  display_value: string;
  norm_value: string;
  scope: string;
}

export interface ValueNode {
  type: 'related_value';
  role: string;
  strength: string;
  scope: string;
  field_path: string;
  norm_value: string;
  display_value: string;
  related_user_count: number;
  doc_count: number;
  collections: string[];
  expandable: boolean;
  attributes?: ValueNodeAttribute[];
}

export interface NodeGroup {
  type: 'identity_group' | 'context_group';
  label: string;
  children: ValueNode[];
}

export interface UserNodeData extends ExplorerUser {
  groups: NodeGroup[];
}

export interface RelatedUser {
  type: 'related_user';
  user_key: string;
  display_name: string;
  identifiers: Record<string, string>;
  record_count: number;
  collection_count: number;
  strength: string;
  scope: string;
  doc_count?: number;
}

export const NAME_KEYS = [
  'full_name', 'fullname', 'full name',
  'name',
  'first_name', 'firstname', 'first name',
  'username', 'user_name', 'user name',
  'email', 'email_address', 'emailaddress',
];

export function resolveFriendlyName(displayName: string, identifiers: Record<string, string> | undefined): string {
  if (!identifiers) return displayName || 'Unknown User';
  const idLower: Record<string, string> = {};
  for (const [k, v] of Object.entries(identifiers)) {
    idLower[k.toLowerCase().trim()] = v;
  }
  for (const key of NAME_KEYS) {
    const val = idLower[key];
    if (val && val.trim()) return val.trim();
  }
  return displayName || 'Unknown User';
}

export function userInitials(name: string): string {
  if (!name) return '?';
  return name.split(/[\s@._-]+/).map(w => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase() || '?';
}

export function extractFieldPrefix(fieldPath: string): string {
  if (!fieldPath) return 'other';
  const leaf = fieldPath.includes('.') ? fieldPath.split('.').pop()! : fieldPath;
  const normalized = leaf.replace(/([a-z0-9])([A-Z])/g, '$1_$2');
  const parts = normalized.split(/[_\-\s]+/);
  return parts[0].toLowerCase();
}

export interface FieldGroup {
  category: string | null;
  items: ValueNode[];
}

export function groupByFieldPrefix(children: ValueNode[]): FieldGroup[] {
  const prefixMap = new Map<string, ValueNode[]>();
  const order: string[] = [];
  for (const child of children) {
    const prefix = extractFieldPrefix(child.field_path);
    if (!prefixMap.has(prefix)) { prefixMap.set(prefix, []); order.push(prefix); }
    prefixMap.get(prefix)!.push(child);
  }
  const result: FieldGroup[] = [];
  for (const prefix of order) {
    const items = prefixMap.get(prefix)!;
    result.push({ category: items.length >= 2 ? prefix : null, items });
  }
  return result;
}

export function makeExpandKey(node: ValueNode): string {
  return `${node.role}:${node.scope}:${node.norm_value}`;
}

export type { ExplorerMeta } from '../../pages/GraphViewer';
