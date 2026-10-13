import type { Dispatch, SetStateAction } from 'react';
import { ChevronRight, ChevronDown, Link2, MapPin, Layers } from 'lucide-react';
import { GrabScrollArea } from './GrabScrollArea';
import { IdentityExplorerValueNodeCard } from './IdentityExplorerValueNodeCard';
import type { UserNodeData, ValueNode, RelatedUser } from './identityExplorerTypes';
import { resolveFriendlyName, userInitials, groupByFieldPrefix } from './identityExplorerTypes';

export interface IdentityExplorerUserDetailSectionProps {
  loadingNode: boolean;
  nodeData: UserNodeData | null;
  openDetailGroupKey: string | null;
  setOpenDetailGroupKey: Dispatch<SetStateAction<string | null>>;
  expandedKeys: Set<string>;
  expandingKey: string | null;
  expandedData: Record<string, { users: RelatedUser[]; nextCursor: string | null; total: number }>;
  toggleExpand: (node: ValueNode) => void | Promise<void>;
  navigateToUser: (userKey: string) => void;
  loadMoreUsers: (node: ValueNode) => void | Promise<void>;
  onScrollRecalc: () => void;
}

export function IdentityExplorerUserDetailSection({
  loadingNode,
  nodeData,
  openDetailGroupKey,
  setOpenDetailGroupKey,
  expandedKeys,
  expandingKey,
  expandedData,
  toggleExpand,
  navigateToUser,
  loadMoreUsers,
  onScrollRecalc,
}: IdentityExplorerUserDetailSectionProps) {
  if (loadingNode) {
    return (
      <GrabScrollArea onScroll={onScrollRecalc} style={{ minHeight: '70vh' }}>
        <style>{`
          @keyframes identityDetailShimmerSweep {
            0% { background-position: 100% 0; }
            100% { background-position: -100% 0; }
          }
        `}</style>
        <div style={{ padding: '2.25rem 2rem 3rem' }}>
          <div style={{ maxWidth: 420, height: 200, margin: '0 auto 2rem', borderRadius: 16, background: 'linear-gradient(90deg, rgba(15,23,42,0.06) 25%, rgba(15,23,42,0.12) 50%, rgba(15,23,42,0.06) 75%)', backgroundSize: '200% 100%', animation: 'identityDetailShimmerSweep 1.25s linear infinite' }} />
          <div style={{ maxWidth: 1040, margin: '0 auto', display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 20 }}>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} style={{ width: 280, height: 146, borderRadius: 14, background: 'linear-gradient(90deg, rgba(15,23,42,0.06) 25%, rgba(15,23,42,0.12) 50%, rgba(15,23,42,0.06) 75%)', backgroundSize: '200% 100%', animation: `identityDetailShimmerSweep 1.25s linear infinite ${i * 0.06}s` }} />
            ))}
          </div>
        </div>
      </GrabScrollArea>
    );
  }

  if (!nodeData) {
    return (
      <GrabScrollArea onScroll={onScrollRecalc} style={{ minHeight: '70vh' }}>
        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>User not found</div>
      </GrabScrollArea>
    );
  }

  const groups = nodeData.groups;
  const friendlyName = resolveFriendlyName(nodeData.display_name, nodeData.identifiers);
  const initials = userInitials(friendlyName);
  const totalLinks = groups.reduce((a, g) => a + g.children.length, 0);

  return (
    <GrabScrollArea onScroll={onScrollRecalc} style={{ minHeight: '70vh' }}>
      <div style={{ padding: '2rem 2.5rem 3rem' }}>
        <div style={{ maxWidth: 420, margin: '0 auto 2rem' }}>
          <div style={{ background: 'rgba(255,255,255,0.98)', border: '1.5px solid rgba(13,148,136,0.3)', borderRadius: 16, overflow: 'hidden', boxShadow: '0 0 40px rgba(13,148,136,0.08), 0 12px 40px rgba(15,23,42,0.08)' }}>
            <div style={{ height: 3, background: 'linear-gradient(90deg, #0d9488, rgba(13,148,136,0.25))' }} />
            <div style={{ padding: '0.9rem 1rem 0.75rem', background: 'linear-gradient(135deg, rgba(13,148,136,0.08) 0%, transparent 100%)', borderBottom: '1px solid rgba(15,23,42,0.08)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.5rem' }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, flexShrink: 0, background: 'rgba(13,148,136,0.15)', border: '2px solid rgba(13,148,136,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.85rem', fontWeight: 800, color: '#0d9488', letterSpacing: '.03em' }}>{initials}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', lineHeight: 1.2, wordBreak: 'break-word' }}>{friendlyName}</div>
                  {friendlyName !== nodeData.display_name && (
                    <div style={{ fontSize: '0.6rem', color: 'rgba(15,23,42,0.45)', marginTop: 2, wordBreak: 'break-word' }}>{nodeData.display_name}</div>
                  )}
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
                {Object.entries(nodeData.identifiers || {}).map(([k, v]) => (
                  <span key={k} style={{ fontSize: '0.58rem', background: 'rgba(15,23,42,0.06)', border: '1px solid rgba(15,23,42,0.1)', borderRadius: 4, padding: '1px 6px', color: 'rgba(15,23,42,0.65)', wordBreak: 'break-word' }}>{k}: {v}</span>
                ))}
              </div>
            </div>
            <div style={{ padding: '0.65rem 1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '1rem' }}>
                {[
                  { label: 'GROUPS', val: groups.length, clr: '#0d9488' },
                  { label: 'LINKS', val: totalLinks, clr: '#38bdf8' },
                  { label: 'REC', val: nodeData.record_count, clr: '#059669' },
                ].map(({ label, val, clr }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'baseline', gap: '0.3rem' }}>
                    <span style={{ fontSize: '0.55rem', color: 'rgba(15,23,42,0.5)', letterSpacing: '.05em' }}>{label}</span>
                    <span style={{ fontSize: '0.95rem', fontWeight: 800, color: clr, lineHeight: 1 }}>{val}</span>
                  </div>
                ))}
              </div>
              <svg width={56} height={56} viewBox="0 0 56 56" style={{ flexShrink: 0 }}>
                {(() => {
                  const cx = 28, cy = 28, r = 20, sw = 7;
                  const circ = 2 * Math.PI * r;
                  const identityCount = groups.filter(g => g.type === 'identity_group').reduce((a, g) => a + g.children.length, 0);
                  const total = identityCount + groups.filter(g => g.type === 'context_group').reduce((a, g) => a + g.children.length, 0);
                  if (!total) return <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(15,23,42,0.08)" strokeWidth={sw} />;
                  const iPct = identityCount / total;
                  const iDash = Math.max(0, iPct * circ - circ * 0.01);
                  const cDash = Math.max(0, (1 - iPct) * circ - circ * 0.01);
                  return (
                    <>
                      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(15,23,42,0.08)" strokeWidth={sw} />
                      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#0d9488" strokeWidth={sw} strokeDasharray={`${iDash} ${circ - iDash}`} strokeDashoffset={circ * 0.25} strokeLinecap="butt" opacity={0.9} />
                      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#6366f1" strokeWidth={sw} strokeDasharray={`${cDash} ${circ - cDash}`} strokeDashoffset={-(iPct * circ) + circ * 0.25} strokeLinecap="butt" opacity={0.9} />
                      <circle cx={cx} cy={cy} r={r - sw / 2 - 1} fill="#f1f5f9" />
                      <text x={cx} y={cy - 3} textAnchor="middle" fill="#0f172a" fontSize={10} fontWeight={800} fontFamily="Syne,sans-serif">{groups.length}</text>
                      <text x={cx} y={cy + 8} textAnchor="middle" fill="rgba(15,23,42,0.5)" fontSize={6.5}>grps</text>
                    </>
                  );
                })()}
              </svg>
            </div>
          </div>
        </div>

        {groups.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem', fontSize: '0.85rem' }}>
            No traversable links found for this user.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%', maxWidth: 1100, margin: '0 auto' }}>
            <div style={{ width: 1, height: 28, background: 'rgba(15,23,42,0.12)', flexShrink: 0 }} />
            <div style={{ width: 'min(720px, 92%)', height: 1, background: 'rgba(15,23,42,0.1)', flexShrink: 0 }} />
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, justifyContent: 'center', alignItems: 'flex-start', width: '100%', padding: '20px 0.5rem 0' }}>
              {groups.map((group, gi) => {
                const isIdentity = group.type === 'identity_group';
                const gColor = isIdentity ? '#0d9488' : '#6366f1';
                const gIcon = isIdentity ? <Link2 size={18} /> : <MapPin size={18} />;
                const groupKey = `group-${gi}`;
                const isOpen = openDetailGroupKey === groupKey;
                const fieldGroups = groupByFieldPrefix(group.children);

                return (
                  <div key={gi} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: '1 1 260px', minWidth: 240, maxWidth: 520 }}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => setOpenDetailGroupKey(prev => (prev === groupKey ? null : groupKey))}
                      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpenDetailGroupKey(prev => (prev === groupKey ? null : groupKey)); } }}
                      style={{
                        width: 'min(100%, 300px)',
                        background: 'rgba(255,255,255,0.98)',
                        border: `1.5px solid ${isOpen ? `${gColor}45` : 'rgba(15,23,42,0.12)'}`,
                        borderRadius: 14,
                        overflow: 'hidden',
                        cursor: 'pointer',
                        boxShadow: isOpen ? `0 8px 28px ${gColor}16` : '0 4px 18px rgba(15,23,42,0.06)',
                        transition: 'border-color 0.15s, box-shadow 0.15s',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.borderColor = `${gColor}38`;
                        e.currentTarget.style.boxShadow = `0 8px 26px ${gColor}12`;
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.borderColor = isOpen ? `${gColor}45` : 'rgba(15,23,42,0.12)';
                        e.currentTarget.style.boxShadow = isOpen ? `0 8px 28px ${gColor}16` : '0 4px 18px rgba(15,23,42,0.06)';
                      }}
                    >
                      <div style={{ height: 3, background: `linear-gradient(90deg, ${gColor}, ${gColor}33)` }} />
                      <div style={{ padding: '0.75rem 1rem', display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
                        <div style={{ width: 40, height: 40, borderRadius: 11, flexShrink: 0, background: `${gColor}14`, border: `2px solid ${gColor}35`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: gColor }}>
                          {gIcon}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f172a', lineHeight: 1.2 }}>{group.label}</div>
                          <div style={{ fontSize: '0.62rem', color: 'rgba(15,23,42,0.48)', marginTop: 3 }}>{group.children.length} links</div>
                        </div>
                        {isOpen ? <ChevronDown size={18} style={{ color: gColor, flexShrink: 0 }} /> : <ChevronRight size={18} style={{ color: gColor, flexShrink: 0 }} />}
                      </div>
                    </div>

                    {isOpen && (
                      <>
                        <div style={{ width: 1, height: 20, background: `${gColor}30`, flexShrink: 0 }} />
                        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, paddingBottom: '1rem' }}>
                          {fieldGroups.map((fg, fgi) => (
                            <div key={`fg-${gi}-${fgi}`} style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
                              {fg.category && (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.25rem 0.6rem', borderRadius: 8, background: `${gColor}0d`, border: `1px solid ${gColor}22` }}>
                                  <Layers size={12} style={{ color: gColor, opacity: 0.85 }} />
                                  <span style={{ fontSize: '0.68rem', fontWeight: 700, color: gColor, textTransform: 'capitalize', fontFamily: "Syne,sans-serif" }}>{fg.category}</span>
                                  <span style={{ fontSize: '0.58rem', color: 'rgba(15,23,42,0.45)'}}>{fg.items.length}</span>
                                </div>
                              )}
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'center', width: '100%' }}>
                                {fg.items.map((child, ci) => (
                                  <IdentityExplorerValueNodeCard
                                    key={`${gi}-${fgi}-${ci}`}
                                    child={child}
                                    ci={fgi * 10000 + ci}
                                    gi={gi}
                                    gColor={gColor}
                                    expandedKeys={expandedKeys}
                                    expandingKey={expandingKey}
                                    expandedData={expandedData}
                                    toggleExpand={toggleExpand}
                                    navigateToUser={navigateToUser}
                                    loadMoreUsers={loadMoreUsers}
                                  />
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </GrabScrollArea>
  );
}
