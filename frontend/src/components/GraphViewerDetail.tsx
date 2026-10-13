import { Fragment, useCallback, useState } from 'react';
import { X, ArrowLeft, Sparkles } from 'lucide-react';
import type { DetailState, NodeInsight } from './GraphViewerTypes';

/** Theme-aligned styles for the detail sidebar (single source, no inline hex). */
const styles = {
  overlay: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(15, 23, 42, 0.25)',
    zIndex: 900,
    animation: 'fadeIn 0.2s ease',
  },
  panel: {
    position: 'fixed' as const,
    top: 0,
    right: 0,
    width: 'min(55vw, 900px)',
    maxWidth: 900,
    height: '100vh',
    background: 'var(--glass-bg)',
    borderLeft: '1px solid var(--glass-border)',
    boxShadow: '-4px 0 24px rgba(15, 23, 42, 0.08)',
    zIndex: 950,
    display: 'flex',
    flexDirection: 'column' as const,
    animation: 'slideIn 0.3s cubic-bezier(0.4,0,0.2,1)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '1rem 1.25rem',
    borderBottom: '1px solid var(--glass-border)',
    minHeight: 56,
    background: 'var(--bg-dark)',
  },
  title: {
    fontSize: '0.95rem',
    fontWeight: 600,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis' as const,
    whiteSpace: 'nowrap' as const,
    flex: 1,
  },
  closeBtn: {
    width: 28,
    height: 28,
    borderRadius: 6,
    border: '1px solid var(--glass-border)',
    background: 'var(--bg-card)',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    marginLeft: '0.75rem',
    transition: 'all 0.2s',
  },
  closeBtnHover: {
    borderColor: 'var(--primary)',
    color: 'var(--primary)',
    background: 'var(--primary-light)',
  },
  body: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: '1.25rem',
    background: 'var(--bg-page)',
  },
  loadingWrap: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '3rem',
    gap: '0.75rem',
    color: 'var(--text-secondary)',
  },
  spinner: {
    width: 18,
    height: 18,
    border: '2px solid var(--glass-border)',
    borderTopColor: 'var(--primary)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  badge: {
    padding: '3px 10px',
    borderRadius: 10,
    fontSize: '0.7rem',
    fontWeight: 500,
    background: 'var(--primary-light)',
    color: 'var(--primary)',
    border: '1px solid rgba(13,148,136,0.25)',
  },
  badgeSecondary: {
    padding: '3px 10px',
    borderRadius: 10,
    fontSize: '0.7rem',
    fontWeight: 500,
    background: 'rgba(56,189,248,0.12)',
    color: '#0ea5e9',
    border: '1px solid rgba(56,189,248,0.25)',
  },
  backBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '0.4rem',
    background: 'var(--bg-card)',
    border: '1px solid var(--glass-border)',
    borderRadius: 6,
    padding: '0.4rem 0.75rem',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    fontSize: '0.78rem',
    marginBottom: '1rem',
    transition: 'all 0.2s',
  },
  conceptCard: {
    background: 'var(--bg-card)',
    border: '1px solid var(--glass-border)',
    borderRadius: 8,
    padding: '0.75rem 1rem',
    marginBottom: '0.5rem',
    cursor: 'pointer',
    transition: 'all 0.2s',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  tableWrap: {
    overflowX: 'auto' as const,
    overflowY: 'auto' as const,
    maxHeight: 'calc(100vh - 220px)',
    borderRadius: 8,
    border: '1px solid var(--glass-border)',
    background: 'var(--bg-dark)',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: '0.78rem',
    fontFamily: "'IBM Plex Mono', 'Consolas', monospace",
  },
  th: {
    padding: '0.6rem 0.75rem',
    background: 'var(--bg-card)',
    color: 'var(--primary)',
    fontWeight: 600,
    fontSize: '0.7rem',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
    textAlign: 'left' as const,
    whiteSpace: 'nowrap' as const,
    borderBottom: '2px solid var(--primary)',
    position: 'sticky' as const,
    top: 0,
    zIndex: 1,
  },
  td: {
    padding: '0.5rem 0.75rem',
    borderBottom: '1px solid var(--glass-border)',
    color: 'var(--text-primary)',
    maxWidth: 200,
    overflow: 'hidden',
    textOverflow: 'ellipsis' as const,
    whiteSpace: 'nowrap' as const,
  },
  tdKey: {
    color: 'var(--primary)',
    fontWeight: 500,
    width: 140,
    verticalAlign: 'top' as const,
  },
  collectionPill: {
    background: 'var(--primary-light)',
    color: 'var(--primary)',
    padding: '2px 8px',
    borderRadius: 10,
    fontSize: '0.68rem',
    fontWeight: 500,
    border: '1px solid rgba(13,148,136,0.25)',
  },
  emptyMessage: {
    color: 'var(--text-secondary)',
    fontSize: '0.85rem',
    padding: '2rem 0',
    textAlign: 'center' as const,
  },
  jsonPre: {
    margin: 0,
    whiteSpace: 'pre-wrap' as const,
    color: 'var(--success)',
    fontSize: '0.7rem',
  },
  insightCard: {
    background: 'linear-gradient(135deg, rgba(124,58,237,0.08) 0%, rgba(13,148,136,0.08) 100%)',
    border: '1px solid rgba(124,58,237,0.25)',
    borderRadius: 12,
    padding: '1rem 1.25rem',
    marginBottom: '1rem',
  },
  insightHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginBottom: '0.75rem',
  },
  insightTypeBadge: {
    padding: '3px 10px',
    borderRadius: 10,
    fontSize: '0.7rem',
    fontWeight: 600,
    background: 'rgba(124,58,237,0.15)',
    color: '#7c3aed',
    border: '1px solid rgba(124,58,237,0.3)',
  },
  insightTitle: {
    fontSize: '1rem',
    fontWeight: 700,
    color: 'var(--text-primary)',
    margin: '0 0 0.25rem',
  },
  insightSummary: {
    fontSize: '0.82rem',
    color: 'var(--text-secondary)',
    lineHeight: 1.5,
    margin: '0 0 0.75rem',
  },
  insightPropsGrid: {
    display: 'grid',
    gridTemplateColumns: 'auto 1fr',
    gap: '0.35rem 0.75rem',
    fontSize: '0.78rem',
    marginBottom: '0.5rem',
  },
  insightPropLabel: {
    color: 'var(--primary)',
    fontWeight: 600,
    fontSize: '0.72rem',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  },
  insightPropValue: {
    color: 'var(--text-primary)',
    wordBreak: 'break-word' as const,
  },
  insightRelated: {
    display: 'flex',
    gap: '0.4rem',
    flexWrap: 'wrap' as const,
    marginTop: '0.5rem',
  },
  insightRelatedPill: {
    padding: '2px 8px',
    borderRadius: 10,
    fontSize: '0.68rem',
    fontWeight: 500,
    background: 'rgba(56,189,248,0.12)',
    color: '#0ea5e9',
    border: '1px solid rgba(56,189,248,0.25)',
  },
  insightSkeleton: {
    height: 12,
    borderRadius: 6,
    background: 'linear-gradient(90deg, var(--glass-border) 25%, rgba(124,58,237,0.1) 50%, var(--glass-border) 75%)',
    backgroundSize: '200% 100%',
    animation: 'shimmer 1.5s infinite',
  },
} as const;

interface GraphViewerDetailProps {
  detail: DetailState;
  setDetail: React.Dispatch<React.SetStateAction<DetailState>>;
  onClose: () => void;
  fetchAndShowTable: (fieldName: string, fieldValue: string | null, title: string, historyEntry?: () => void) => void;
  showConceptSummary: (conceptNode: { data: { name: string }; children?: { data: { name: string }; children?: unknown; value?: number }[] }) => void;
  showRowDetail: (row: Record<string, unknown>, prevRestore: () => void) => void;
  goBack: () => void;
}

export function GraphViewerDetail({
  detail,
  setDetail,
  onClose,
  fetchAndShowTable,
  showConceptSummary,
  showRowDetail,
  goBack,
}: GraphViewerDetailProps) {
  if (!detail.open) return null;

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const [searchVal, setSearchVal] = useState('');

  const handleConceptFieldClick = useCallback(
    (fieldName: string) => {
      const currentRestore = () =>
        showConceptSummary({
          data: { name: detail.title },
          children: detail.conceptFields.map(cf => ({
            data: { name: cf.name },
            children: cf.valCount > 0 ? new Array(cf.valCount) : undefined,
            value: cf.totalFreq,
          })),
        });
      setDetail(prev => ({ ...prev, history: [...prev.history, currentRestore] }));
      fetchAndShowTable(fieldName, null, `All "${fieldName}" records`);
    },
    [detail.title, detail.conceptFields, setDetail, showConceptSummary, fetchAndShowTable]
  );

  const handleRowClick = useCallback(
    (row: Record<string, unknown>) => {
      const t = detail.title;
      const restore = () => fetchAndShowTable(t.split('=')[0]?.replace(/"/g, '').trim() || t, null, t);
      showRowDetail(row, restore);
    },
    [detail.title, fetchAndShowTable, showRowDetail]
  );

  const renderInsightCard = (insight: NodeInsight | null, loading: boolean) => {
    if (!loading && !insight) return null;

    if (loading) {
      return (
        <div style={styles.insightCard}>
          <div style={styles.insightHeader}>
            <Sparkles size={16} style={{ color: '#7c3aed', animation: 'spin 2s linear infinite' }} />
            <span style={{ fontSize: '0.78rem', color: '#7c3aed', fontWeight: 600 }}>AI analyzing this entity…</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ ...styles.insightSkeleton, width: '60%', height: 14 }} />
            <div style={{ ...styles.insightSkeleton, width: '90%' }} />
            <div style={{ ...styles.insightSkeleton, width: '75%' }} />
            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: '0.35rem 0.75rem', marginTop: '0.25rem' }}>
              <div style={{ ...styles.insightSkeleton, width: '100%' }} />
              <div style={{ ...styles.insightSkeleton, width: '50%' }} />
              <div style={{ ...styles.insightSkeleton, width: '100%' }} />
              <div style={{ ...styles.insightSkeleton, width: '70%' }} />
            </div>
          </div>
        </div>
      );
    }

    if (!insight) return null;

    return (
      <div style={styles.insightCard}>
        <div style={styles.insightHeader}>
          <Sparkles size={16} style={{ color: '#7c3aed' }} />
          <span style={styles.insightTypeBadge}>{insight.entity_type}</span>
        </div>
        <h4 style={styles.insightTitle}>{insight.title}</h4>
        <p style={styles.insightSummary}>{insight.summary}</p>
        {insight.properties.length > 0 && (
          <div style={styles.insightPropsGrid}>
            {insight.properties.map((prop, i) => (
              <Fragment key={i}>
                <span style={styles.insightPropLabel}>{prop.label}</span>
                <span style={styles.insightPropValue}>{prop.value}</span>
              </Fragment>
            ))}
          </div>
        )}
        {insight.related_entities.length > 0 && (
          <div style={styles.insightRelated}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Related:</span>
            {insight.related_entities.map((entity, i) => (
              <span key={i} style={styles.insightRelatedPill}>{entity}</span>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderContent = () => {
    if (detail.loading)
      return (
        <div style={styles.loadingWrap}>
          <div style={styles.spinner} />
          Loading data…
        </div>
      );

    if (detail.type === 'concept')
      return (
        <div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
            <span style={styles.badge}>{detail.conceptFields.length} fields</span>
          </div>
          {detail.conceptFields.map((f, i) => (
            <div
              key={`${f.name}-${i}`}
              role="button"
              tabIndex={0}
              onClick={() => handleConceptFieldClick(f.name)}
              onKeyDown={e => e.key === 'Enter' && handleConceptFieldClick(f.name)}
              style={styles.conceptCard}
              onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--primary)';
                e.currentTarget.style.transform = 'translateX(4px)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.borderColor = '';
                e.currentTarget.style.transform = '';
              }}
            >
              <span style={{ fontFamily: "var(--font-mono, 'IBM Plex Mono', monospace)", fontSize: '0.82rem', color: 'var(--text-primary)' }}>{f.name}</span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{f.valCount} values · {f.totalFreq} total</span>
            </div>
          ))}
        </div>
      );

    if (detail.type === 'row' && detail.rowData) {
      const rowData = detail.rowData as Record<string, unknown>;
      const allKeys = Object.keys(rowData).filter(k => !String(k).startsWith('_'));
      return (
        <div>
          {detail.history.length > 0 && (
            <button type="button" onClick={goBack} style={styles.backBtn} aria-label="Back to table">
              <ArrowLeft size={14} /> Back to table
            </button>
          )}
          {rowData._collection != null && (
            <div style={{ marginBottom: '1rem' }}>
              <span style={styles.collectionPill}>{String(rowData._collection)}</span>
            </div>
          )}
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              {allKeys.map(key => (
                <tr key={key} style={{ borderBottom: '1px solid var(--glass-border)' }}>
                  <td style={{ ...styles.td, ...styles.tdKey, fontFamily: "var(--font-mono, 'IBM Plex Mono', monospace)", fontSize: '0.75rem' }}>{key}</td>
                  <td style={{ ...styles.td, wordBreak: 'break-word', whiteSpace: 'normal', fontFamily: "var(--font-mono, 'IBM Plex Mono', monospace)", fontSize: '0.75rem' }}>
                    {typeof rowData[key] === 'object' && rowData[key] !== null ? (
                      <pre style={styles.jsonPre}>{JSON.stringify(rowData[key], null, 2)}</pre>
                    ) : (
                      String(rowData[key] ?? '')
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    if (detail.rows.length === 0 && !detail.insightLoading && !detail.insight) return <p style={styles.emptyMessage}>No matching records found.</p>;

    const rows = detail.rows as Record<string, unknown>[];
    const activeField = detail.activeField;

    const handleSearch = (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = searchVal.trim();
      if (!activeField || !trimmed) return;
      fetchAndShowTable(activeField, trimmed, `${activeField} = "${trimmed}"`);
      setSearchVal('');
    };

    return (
      <div>
        {renderInsightCard(detail.insight, detail.insightLoading)}
        {detail.history.length > 0 && (
          <button type="button" onClick={goBack} style={styles.backBtn} aria-label="Back">
            <ArrowLeft size={14} /> Back
          </button>
        )}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          <span style={styles.badge}>{detail.total} record{detail.total !== 1 ? 's' : ''}</span>
          {detail.equivalentFields.length > 1 && (
            <span style={styles.badgeSecondary}>Also matched: {detail.equivalentFields.slice(1).join(', ')}</span>
          )}
        </div>

        {/* Search bar — search for other values of the same field */}
        {activeField && (
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <input
              type="text"
              value={searchVal}
              onChange={e => setSearchVal(e.target.value)}
              placeholder={`Search other ${activeField} values…`}
              style={{
                flex: 1,
                padding: '0.4rem 0.75rem',
                fontSize: '0.8rem',
                background: 'var(--bg-card)',
                border: '1px solid var(--glass-border)',
                borderRadius: '6px',
                color: 'var(--text-primary)',
                outline: 'none',
              }}
            />
            <button
              type="submit"
              className="btn btn-secondary"
              style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem', flexShrink: 0 }}
            >
              Search
            </button>
          </form>
        )}

        <div style={styles.tableWrap}>
          <table style={styles.table}>
            <thead>
              <tr>
                {detail.columns.map(col => {
                  const isActive = col === activeField || (detail.equivalentFields.includes(col) && col !== '_collection');
                  return (
                    <th
                      key={col}
                      style={{
                        ...styles.th,
                        ...(isActive ? {
                          background: 'rgba(13,148,136,0.18)',
                          borderBottom: '2px solid var(--primary)',
                          color: 'var(--primary)',
                        } : {}),
                      }}
                    >
                      {col === '_collection' ? 'Collection' : col}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={i}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleRowClick(row)}
                  onKeyDown={e => e.key === 'Enter' && handleRowClick(row)}
                  style={{
                    borderBottom: '1px solid var(--glass-border)',
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                    background: i % 2 === 1 ? 'var(--bg-card)' : undefined,
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--primary-light)';
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = i % 2 === 1 ? 'var(--bg-card)' : '';
                  }}
                >
                  {detail.columns.map(col => {
                    const isActive = col === activeField || (detail.equivalentFields.includes(col) && col !== '_collection');
                    return (
                      <td
                        key={col}
                        style={{
                          ...styles.td,
                          ...(isActive ? { background: 'rgba(13,148,136,0.06)', fontWeight: 600 } : {}),
                        }}
                      >
                        {col === '_collection' ? (
                          <span style={styles.collectionPill}>{String(row[col] ?? '')}</span>
                        ) : (
                          row[col] != null ? String(row[col]) : ''
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <>
      <div role="presentation" onClick={onClose} style={styles.overlay} aria-hidden />
      <div style={styles.panel} role="dialog" aria-modal aria-labelledby="graph-detail-title">
        <div style={styles.header}>
          <span id="graph-detail-title" style={styles.title}>{detail.title}</span>
          <button
            type="button"
            onClick={onClose}
            style={styles.closeBtn}
            aria-label="Close panel"
            onMouseEnter={e => Object.assign(e.currentTarget.style, styles.closeBtnHover)}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--glass-border)';
              e.currentTarget.style.color = 'var(--text-secondary)';
              e.currentTarget.style.background = 'var(--bg-card)';
            }}
          >
            <X size={14} />
          </button>
        </div>
        <div style={styles.body}>{renderContent()}</div>
      </div>
    </>
  );
}
