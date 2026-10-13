import { Users } from 'lucide-react';
import type { RefObject, MutableRefObject } from 'react';
import { GrabScrollArea } from './GrabScrollArea';
import type { ExplorerUser } from './identityExplorerTypes';
import { resolveFriendlyName, userInitials } from './identityExplorerTypes';

export interface IdentityExplorerOverviewSectionProps {
  totalUsers: number;
  loadingPage: boolean;
  filteredUsers: ExplorerUser[];
  isSearchActive: boolean;
  searchQ: string;
  searchLoading: boolean;
  searchResults: ExplorerUser[];
  currentPageIdx: number;
  PAGE_LIMIT: number;
  nextCursor: string | null;
  goNextPage: () => void;
  goPrevPage: () => void;
  selectUser: (userKey: string) => void;
  overviewInnerRef: RefObject<HTMLDivElement | null>;
  overviewRootRef: RefObject<HTMLDivElement | null>;
  userNodeRefs: MutableRefObject<(HTMLDivElement | null)[]>;
  overviewTreeLines: { svgPaths: string[]; svgW: number; svgH: number };
  onScrollRecalc: () => void;
}

export function IdentityExplorerOverviewSection({
  totalUsers,
  loadingPage,
  filteredUsers,
  isSearchActive,
  searchQ,
  searchLoading,
  searchResults,
  currentPageIdx,
  PAGE_LIMIT,
  nextCursor,
  goNextPage,
  goPrevPage,
  selectUser,
  overviewInnerRef,
  overviewRootRef,
  userNodeRefs,
  overviewTreeLines,
  onScrollRecalc,
}: IdentityExplorerOverviewSectionProps) {
  return (
    <GrabScrollArea onScroll={onScrollRecalc} style={{ minHeight: '70vh' }}>
      <style>{`
        @keyframes identityShimmerSweep {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
      `}</style>
      {loadingPage ? (
        <div style={{ padding: '2.5rem 2rem 3rem', minWidth: 'max-content' }}>
          <div style={{ width: 240, height: 110, margin: '0 auto 2rem', borderRadius: 14, background: 'linear-gradient(90deg, rgba(15,23,42,0.06) 25%, rgba(15,23,42,0.12) 50%, rgba(15,23,42,0.06) 75%)', backgroundSize: '200% 100%', animation: 'identityShimmerSweep 1.3s linear infinite' }} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, justifyContent: 'center', maxWidth: 1100, margin: '0 auto' }}>
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} style={{ width: 170, height: 72, borderRadius: 12, background: 'linear-gradient(90deg, rgba(15,23,42,0.06) 25%, rgba(15,23,42,0.12) 50%, rgba(15,23,42,0.06) 75%)', backgroundSize: '200% 100%', animation: `identityShimmerSweep 1.3s linear infinite ${i * 0.05}s` }} />
            ))}
          </div>
        </div>
      ) : filteredUsers.length === 0 && !searchLoading ? (
        <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          {isSearchActive ? `No users found matching "${searchQ}"` : 'No users found'}
        </div>
      ) : (
        <div ref={overviewInnerRef} style={{ position: 'relative', padding: '48px 40px 60px', minWidth: 'max-content', minHeight: '100%', boxSizing: 'border-box' }}>
          <svg style={{ position: 'absolute', top: 0, left: 0, width: overviewTreeLines.svgW || '100%', height: overviewTreeLines.svgH || '100%', pointerEvents: 'none', overflow: 'visible' }}>
            {overviewTreeLines.svgPaths.map((d, i) => (
              <path key={i} d={d} stroke="rgba(15,23,42,0.15)" strokeWidth={1.5} fill="none" strokeLinejoin="round" />
            ))}
          </svg>

          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 60 }}>
            <div ref={overviewRootRef} style={{ width: 240, background: 'rgba(255,255,255,0.98)', border: '1.5px solid rgba(13,148,136,0.3)', borderRadius: 16, overflow: 'hidden', boxShadow: '0 0 40px rgba(13,148,136,0.08), 0 12px 40px rgba(15,23,42,0.08)' }}>
              <div style={{ height: 3, background: 'linear-gradient(90deg, #0d9488, rgba(13,148,136,0.25))' }} />
              <div style={{ padding: '0.9rem 1rem', display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, flexShrink: 0, background: 'rgba(13,148,136,0.15)', border: '2px solid rgba(13,148,136,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Users size={20} style={{ color: '#0d9488' }} />
                </div>
                <div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0f172a', lineHeight: 1.2 }}>All Users</div>
                  <div style={{ fontSize: '0.65rem', color: 'rgba(15,23,42,0.5)', marginTop: 2 }}>{totalUsers.toLocaleString()} nodes</div>
                </div>
              </div>
              <div style={{ padding: '0.5rem 1rem', borderTop: '1px solid rgba(15,23,42,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)' }}>
                {isSearchActive ? (
                  <span style={{ color: '#0d9488' }}>
                    {searchLoading ? 'Searching…' : `${searchResults.length} match${searchResults.length !== 1 ? 'es' : ''}`}
                  </span>
                ) : (
                  <span>{currentPageIdx * PAGE_LIMIT + 1}–{Math.min((currentPageIdx + 1) * PAGE_LIMIT, totalUsers)}</span>
                )}
                {!isSearchActive && (
                  <div style={{ display: 'flex', gap: '0.3rem' }}>
                    <button type="button" data-no-drag-scroll onClick={goPrevPage} disabled={currentPageIdx === 0 || loadingPage}
                      style={{ padding: '2px 8px', fontSize: '0.65rem', cursor: 'pointer', background: currentPageIdx === 0 ? 'transparent' : 'rgba(13,148,136,0.1)', border: '1px solid rgba(15,23,42,0.12)', borderRadius: 4, color: currentPageIdx === 0 ? 'rgba(15,23,42,0.3)' : '#0d9488' }}>
                      Prev
                    </button>
                    <button type="button" data-no-drag-scroll onClick={goNextPage} disabled={!nextCursor || loadingPage}
                      style={{ padding: '2px 8px', fontSize: '0.65rem', cursor: 'pointer', background: !nextCursor ? 'transparent' : 'rgba(13,148,136,0.1)', border: '1px solid rgba(15,23,42,0.12)', borderRadius: 4, color: !nextCursor ? 'rgba(15,23,42,0.3)' : '#0d9488' }}>
                      Next
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, justifyContent: 'center' }}>
            {filteredUsers.map((user, i) => {
              const friendlyName = resolveFriendlyName(user.display_name, user.identifiers);
              const initials = userInitials(friendlyName);
              return (
                <div
                  key={user.user_key}
                  ref={(el: HTMLDivElement | null) => { userNodeRefs.current[i] = el; }}
                  onClick={() => selectUser(user.user_key)}
                  style={{
                    width: 170, background: 'rgba(255,255,255,0.98)',
                    border: '1px solid rgba(15,23,42,0.12)', borderRadius: 12,
                    overflow: 'hidden', cursor: 'pointer',
                    boxShadow: '0 4px 16px rgba(15,23,42,0.06)',
                    transition: 'all 0.15s ease',
                    flexShrink: 0,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(13,148,136,0.4)'; e.currentTarget.style.boxShadow = '0 6px 24px rgba(13,148,136,0.12)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(15,23,42,0.12)'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(15,23,42,0.06)'; e.currentTarget.style.transform = 'translateY(0)'; }}
                >
                  <div style={{ padding: '0.7rem 0.7rem 0.55rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <div style={{ width: 34, height: 34, borderRadius: 9, flexShrink: 0, background: 'rgba(13,148,136,0.12)', border: '1.5px solid rgba(13,148,136,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 800, color: '#0d9488' }}>{initials}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '0.76rem', fontWeight: 700, color: '#0f172a', lineHeight: 1.15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{friendlyName}</div>
                      <div style={{ fontSize: '0.55rem', color: 'rgba(15,23,42,0.5)', marginTop: 1 }}>{user.record_count} rec &middot; {user.collection_count} col</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </GrabScrollArea>
  );
}
