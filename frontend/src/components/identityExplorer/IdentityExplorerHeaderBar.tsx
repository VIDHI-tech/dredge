import { RefreshCw, Users, ArrowLeft } from 'lucide-react';
import type { ExplorerMeta } from './identityExplorerTypes';

export interface IdentityExplorerHeaderBarProps {
  explorerMeta: ExplorerMeta;
  totalUsers: number;
  selectedUserKey: string | null;
  goBack: () => void;
  searchQ: string;
  setSearchQ: (q: string) => void;
  loading: boolean;
  refreshing: boolean;
  viewMode: string;
  onBuildUserTree: (forceRefresh?: boolean) => void;
}

export function IdentityExplorerHeaderBar({
  explorerMeta,
  totalUsers,
  selectedUserKey,
  goBack,
  searchQ,
  setSearchQ,
  loading,
  refreshing,
  viewMode,
  onBuildUserTree,
}: IdentityExplorerHeaderBarProps) {
  return (
    <div
      style={{
        padding: '1.25rem 1.5rem',
        borderBottom: '1px solid var(--glass-border)',
        background: 'rgba(255,255,255,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '0.75rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
        {selectedUserKey && (
          <button type="button" onClick={goBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: '0.2rem', flexShrink: 0, display: 'flex', alignItems: 'center' }}>
            <ArrowLeft size={18} />
          </button>
        )}
        <Users size={18} style={{ color: 'var(--primary)', flexShrink: 0 }} />
        <h3 style={{ fontSize: '1rem', fontWeight: 700, letterSpacing: '0.02em', color: '#0d9488', margin: 0 }}>
          Identity Explorer
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ background: 'var(--primary-light)', color: 'var(--primary)', padding: '2px 10px', borderRadius: '10px', fontSize: '0.72rem', fontWeight: 600, border: '1px solid rgba(13,148,136,0.25)' }}>
            {totalUsers || explorerMeta.total_users || 0} users
          </span>
          <span style={{ background: 'rgba(56,189,248,0.15)', color: '#0ea5e9', padding: '2px 10px', borderRadius: '10px', fontSize: '0.72rem', fontWeight: 600, border: '1px solid rgba(56,189,248,0.25)' }}>
            {explorerMeta.total_mentions || 0} links
          </span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
        {!selectedUserKey && (
          <input
            style={{
              background: 'rgba(255,255,255,0.9)', border: '1px solid rgba(15,23,42,0.12)',
              borderRadius: '7px', color: '#0f172a', padding: '.38rem .7rem', fontSize: '.78rem',
              width: '200px', minWidth: '140px',
            }}
            placeholder="Search all users..."
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
          />
        )}
        <button className="btn btn-primary" onClick={() => onBuildUserTree()} disabled={loading}
          style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }}>
          {loading && viewMode === 'usertree' && !refreshing ? 'Building...' : 'Build Index'}
        </button>
        <button className="btn btn-secondary" onClick={() => onBuildUserTree(true)} disabled={loading}
          style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <RefreshCw size={14} style={refreshing && viewMode === 'usertree' ? { animation: 'spin 0.8s linear infinite' } : undefined} />
          Refresh
        </button>
      </div>
    </div>
  );
}
