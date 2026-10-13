import { ChevronRight, ChevronDown } from 'lucide-react';
import type { ValueNode, RelatedUser } from './identityExplorerTypes';
import { makeExpandKey, resolveFriendlyName, userInitials } from './identityExplorerTypes';

export interface IdentityExplorerValueNodeCardProps {
  child: ValueNode;
  ci: number;
  gi: number;
  gColor: string;
  expandedKeys: Set<string>;
  expandingKey: string | null;
  expandedData: Record<string, { users: RelatedUser[]; nextCursor: string | null; total: number }>;
  toggleExpand: (node: ValueNode) => void | Promise<void>;
  navigateToUser: (userKey: string) => void;
  loadMoreUsers: (node: ValueNode) => void | Promise<void>;
}

export function IdentityExplorerValueNodeCard({
  child,
  ci,
  gi,
  gColor,
  expandedKeys,
  expandingKey,
  expandedData,
  toggleExpand,
  navigateToUser,
  loadMoreUsers,
}: IdentityExplorerValueNodeCardProps) {
  const expandKey = makeExpandKey(child);
  const isExpanded = expandedKeys.has(expandKey);
  const isExpanding = expandingKey === expandKey;
  const expandInfo = expandedData[expandKey];
  const relatedUsers = expandInfo?.users || [];
  const hasMore = !!expandInfo?.nextCursor;
  const remaining = expandInfo ? Math.max(0, expandInfo.total - expandInfo.users.length) : 0;
  const strengthColor = child.strength === 'strong' ? '#0d9488' : child.strength === 'medium' ? '#0ea5e9' : '#6366f1';
  const pathLeaf = child.field_path.includes('.') ? child.field_path.split('.').pop()! : child.field_path;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, marginBottom: 4 }}>
      <div
        role={child.expandable ? 'button' : undefined}
        tabIndex={child.expandable ? 0 : undefined}
        onClick={() => child.expandable && void toggleExpand(child)}
        onKeyDown={e => { if (child.expandable && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); void toggleExpand(child); } }}
        title={child.display_value}
        style={{
          width: 200,
          background: 'rgba(255,255,255,0.98)',
          border: `1px solid ${isExpanded ? `${gColor}55` : 'rgba(15,23,42,0.12)'}`,
          borderRadius: 12,
          overflow: 'hidden',
          cursor: child.expandable ? 'pointer' : 'default',
          boxShadow: isExpanded ? `0 6px 22px ${gColor}18` : '0 4px 16px rgba(15,23,42,0.06)',
          transition: 'border-color 0.15s, box-shadow 0.15s',
          flexShrink: 0,
        }}
        onMouseEnter={e => {
          if (!child.expandable) return;
          e.currentTarget.style.borderColor = `${gColor}44`;
          e.currentTarget.style.boxShadow = `0 6px 24px ${gColor}14`;
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = isExpanded ? `${gColor}55` : 'rgba(15,23,42,0.12)';
          e.currentTarget.style.boxShadow = isExpanded ? `0 6px 22px ${gColor}18` : '0 4px 16px rgba(15,23,42,0.06)';
        }}
      >
        <div style={{ height: 2, background: `linear-gradient(90deg, ${strengthColor}, ${gColor}44)` }} />
        <div style={{ padding: '0.65rem 0.7rem 0.5rem', display: 'flex', alignItems: 'flex-start', gap: '0.45rem' }}>
          <div style={{
            width: 30, height: 30, borderRadius: 8, flexShrink: 0,
            background: `${strengthColor}18`, border: `1.5px solid ${strengthColor}40`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {child.expandable ? (
              isExpanding && !isExpanded
                ? <div style={{ width: 12, height: 12, border: '1.5px solid var(--glass-border)', borderTopColor: gColor, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                : isExpanded
                  ? <ChevronDown size={14} style={{ color: gColor }} />
                  : <ChevronRight size={14} style={{ color: gColor }} />
            ) : (
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: strengthColor }} />
            )}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: '0.62rem', fontWeight: 600, color: 'rgba(15,23,42,0.45)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{pathLeaf}</div>
            <div style={{ fontSize: '0.74rem', fontWeight: 700, color: '#0f172a', lineHeight: 1.25, marginTop: 2, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', wordBreak: 'break-word' }}>{child.display_value}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.2rem', marginTop: 6 }}>
              <span style={{ fontSize: '0.52rem', fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: `${strengthColor}15`, color: strengthColor }}>{child.strength}</span>
              {child.related_user_count > 0 && (
                <span style={{ fontSize: '0.52rem', color: 'rgba(15,23,42,0.5)'}}>{child.related_user_count} users</span>
              )}
              <span style={{ fontSize: '0.52rem', color: 'rgba(15,23,42,0.45)'}}>{child.doc_count} doc</span>
            </div>
          </div>
        </div>
        {child.attributes && child.attributes.length > 0 && (
          <div style={{ padding: '0 0.65rem 0.55rem', display: 'flex', flexWrap: 'wrap', gap: '0.2rem' }}>
            {child.attributes.slice(0, 8).map((attr, ai) => {
              const shortField = attr.field_path.includes('.') ? attr.field_path.split('.').pop() : attr.field_path;
              return (
                <span
                  key={ai}
                  style={{
                    fontSize: '0.55rem',
                    background: 'rgba(99,102,241,0.06)',
                    border: '1px solid rgba(99,102,241,0.12)',
                    borderRadius: 4,
                    padding: '1px 5px',
                    color: 'rgba(15,23,42,0.65)',
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={`${shortField}: ${attr.display_value}`}
                >
                  <span style={{ fontWeight: 600, color: 'rgba(15,23,42,0.45)' }}>{shortField}:</span>{' '}{attr.display_value}
                </span>
              );
            })}
            {child.attributes.length > 8 && (
              <span style={{ fontSize: '0.55rem', color: 'rgba(15,23,42,0.4)' }}>+{child.attributes.length - 8}</span>
            )}
          </div>
        )}
      </div>

      {isExpanded && (
        <>
          <div style={{ width: 1, height: 14, background: `${strengthColor}35`, flexShrink: 0 }} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'center', maxWidth: 'min(920px, 100%)', padding: '0 0.5rem 0.5rem' }}>
            {relatedUsers.length > 0 ? relatedUsers.map((ru, ri) => {
              const ruName = resolveFriendlyName(ru.display_name, ru.identifiers);
              const ruInitials = userInitials(ruName);
              return (
                <div
                  key={ri}
                  onClick={() => navigateToUser(ru.user_key)}
                  style={{
                    width: 168,
                    background: 'rgba(255,255,255,0.98)',
                    border: '1px solid rgba(13,148,136,0.22)',
                    borderRadius: 11,
                    overflow: 'hidden',
                    cursor: 'pointer',
                    boxShadow: '0 4px 14px rgba(13,148,136,0.08)',
                    transition: 'transform 0.12s, box-shadow 0.12s',
                    flexShrink: 0,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 8px 22px rgba(13,148,136,0.14)'; }}
                  onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = '0 4px 14px rgba(13,148,136,0.08)'; }}
                >
                  <div style={{ height: 2, background: 'linear-gradient(90deg, #0d9488, rgba(13,148,136,0.2))' }} />
                  <div style={{ padding: '0.55rem 0.65rem', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, flexShrink: 0, background: 'rgba(13,148,136,0.12)', border: '1.5px solid rgba(13,148,136,0.28)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.62rem', fontWeight: 800, color: '#0d9488' }}>{ruInitials}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ruName}</div>
                      <div style={{ fontSize: '0.52rem', color: 'rgba(15,23,42,0.5)', marginTop: 2 }}>{ru.record_count} rec · {ru.collection_count} col{ru.doc_count != null ? ` · ${ru.doc_count} doc` : ''}</div>
                    </div>
                    <ChevronRight size={14} style={{ color: 'rgba(15,23,42,0.22)', flexShrink: 0 }} />
                  </div>
                </div>
              );
            }) : !isExpanding && (
              <div style={{ padding: '0.5rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>No related users</div>
            )}
            {isExpanding && (
              <div style={{ padding: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem', width: '100%', justifyContent: 'center' }}>
                <div style={{ width: 14, height: 14, border: '1.5px solid var(--glass-border)', borderTopColor: gColor, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Loading…</span>
              </div>
            )}
            {hasMore && !isExpanding && (
              <button
                type="button"
                data-no-drag-scroll
                onClick={(e) => { e.stopPropagation(); void loadMoreUsers(child); }}
                className="btn btn-secondary"
                style={{ padding: '0.4rem 0.85rem', fontSize: '0.72rem', borderColor: `${gColor}40`, color: gColor }}
              >
                Load more ({remaining} left)
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
