import { Fragment, type ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

/** Use only 1st-level keys as columns. Nested objects shown in expanded row. */
function normalizeResultsForTable(results: any[]): { rows: any[]; columns: string[] } {
    if (!results || results.length === 0) return { rows: [], columns: [] };
    const rows = results;
    const keySet = new Set<string>();
    rows.forEach((r) => Object.keys(r).forEach((k) => keySet.add(k)));
    const columns = Array.from(keySet);
    return { rows, columns };
}

function renderCellValue(val: any, truncate = true): ReactNode {
    if (val === null || val === undefined) {
        return <span style={{ color: 'var(--text-secondary)', fontStyle: 'italic', fontSize: '0.7rem' }}>null</span>;
    }
    if (Array.isArray(val)) {
        const len = val.length;
        if (len === 0) return <span style={{ color: 'var(--text-secondary)', fontSize: '0.7rem' }}>[]</span>;
        const first = val[0];
        const isPrimitive = first === null || first === undefined || typeof first !== 'object';
        if (isPrimitive) {
            const str = val.map((v) => v == null ? 'null' : String(v)).join(', ');
            if (truncate && str.length > 50) return <span title={str} style={{ fontSize: '0.78rem' }}>{str.slice(0, 50)}…</span>;
            return <span style={{ fontSize: '0.78rem' }}>{str}</span>;
        }
        return <span style={{ color: 'var(--primary)', fontSize: '0.7rem', fontStyle: 'italic' }} title={JSON.stringify(val)}>[{len} items] — expand to view</span>;
    }
    if (typeof val === 'object') {
        return <span style={{ color: 'var(--primary)', fontSize: '0.7rem', fontStyle: 'italic' }} title={JSON.stringify(val)}>[Object] — expand to view</span>;
    }
    const str = String(val);
    if (truncate && str.length > 40) {
        return <span title={str}>{str.slice(0, 40)}…</span>;
    }
    return str;
}

function renderExpandedRow(row: any): ReactNode {
    const entries = Object.entries(row).filter(([k]) => k !== '_id');
    const renderNested = (obj: any, indent = 0): ReactNode => {
        if (obj === null || obj === undefined) return <em>null</em>;
        if (Array.isArray(obj)) {
            return <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: 'var(--success)', fontSize: '0.7rem' }}>{JSON.stringify(obj, null, 2)}</pre>;
        }
        if (typeof obj === 'object') {
            return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginTop: indent ? '0.25rem' : 0, marginLeft: indent ? '0.75rem' : 0, borderLeft: indent ? '2px solid var(--glass-border)' : 'none', paddingLeft: indent ? '0.5rem' : 0 }}>
                    {Object.entries(obj).map(([k, v]) => (
                        <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem', fontSize: '0.78rem' }}>
                            <span style={{ color: 'var(--primary)', fontSize: '0.72rem' }}>{k}:
                                {v !== null && v !== undefined && typeof v === 'object' && !Array.isArray(v)
                                    ? renderNested(v, indent + 1)
                                    : <span style={{ color: 'var(--text-primary)', wordBreak: 'break-word' }}>{v !== null && v !== undefined ? String(v) : <em>null</em>}</span>}
                            </span>
                        </div>
                    ))}
                </div>
            );
        }
        return String(obj);
    };
    const expandEntry = (key: string, val: any) => {
        if (key === 'schema' && val && typeof val === 'object') {
            return (
                <details style={{ marginTop: '0.25rem' }}>
                    <summary style={{ cursor: 'pointer', color: 'var(--primary)', fontSize: '0.7rem' }}>View JSON schema</summary>
                    <pre style={{ margin: '0.5rem 0 0', whiteSpace: 'pre-wrap', color: 'var(--success)', fontSize: '0.68rem', maxHeight: '200px', overflow: 'auto' }}>{JSON.stringify(val, null, 2)}</pre>
                </details>
            );
        }
        if (val && typeof val === 'object' && !Array.isArray(val)) {
            return renderNested(val);
        }
        if (Array.isArray(val)) {
            return <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: 'var(--success)', fontSize: '0.7rem' }}>{JSON.stringify(val, null, 2)}</pre>;
        }
        return val !== null && val !== undefined ? String(val) : <span style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>null</span>;
    };
    return (
        <tr>
            <td colSpan={999} style={{ padding: 0, background: 'rgba(13, 148, 136, 0.04)' }}>
                <div style={{
                    padding: '1rem 1.25rem', borderLeft: '3px solid var(--primary)',
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.5rem'
                }}>
                    {entries.map(([key, val]) => (
                        <div key={key} style={{
                            display: 'flex', flexDirection: 'column', gap: '0.25rem', padding: '0.4rem 0.6rem',
                            background: 'rgba(15,23,42,0.04)', borderRadius: '6px', fontSize: '0.78rem',
                            alignItems: 'flex-start'
                        }}>
                            <span style={{
                                color: 'var(--primary)', fontWeight: 600, fontFamily: "'Consolas', monospace",
                                fontSize: '0.72rem', flexShrink: 0, paddingTop: '1px'
                            }}>{key}</span>
                            <span style={{
                                color: 'var(--text-primary)', wordBreak: 'break-word',
                                fontFamily: "'Consolas', monospace", fontSize: '0.72rem', lineHeight: 1.5
                            }}>
                                {expandEntry(key, val)}
                            </span>
                        </div>
                    ))}
                </div>
            </td>
        </tr>
    );
}

export interface NlpResultsTableProps {
    results: any[];
    msgId: string;
    expandedRowIndex: number | null;
    onRowExpand: (rowIdx: number) => void;
}

export function NlpResultsTable({ results, expandedRowIndex, onRowExpand }: NlpResultsTableProps) {
    const { rows, columns } = normalizeResultsForTable(results);

    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {results.length} results
                </span>
                <span style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                    Click a row to expand
                </span>
            </div>
            <div style={{ overflowX: 'auto', maxHeight: '500px', overflowY: 'auto', borderRadius: '8px', border: '1px solid var(--glass-border)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem', fontFamily: "'Consolas', monospace" }}>
                    <thead>
                        <tr>
                            <th style={{
                                padding: '0.5rem 0.4rem', background: 'var(--bg-card)', color: 'var(--primary)',
                                fontWeight: 600, fontSize: '0.7rem', borderBottom: '2px solid var(--primary)',
                                position: 'sticky', top: 0, zIndex: 1, width: '28px'
                            }}></th>
                            {columns.map(key => (
                                <th key={key} style={{
                                    padding: '0.5rem 0.6rem', background: 'var(--bg-card)', color: 'var(--primary)',
                                    fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase',
                                    letterSpacing: '0.04em', textAlign: 'left', whiteSpace: 'nowrap',
                                    borderBottom: '2px solid var(--primary)', position: 'sticky', top: 0, zIndex: 1
                                }}>{key}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows?.map((row, i) => {
                            const isExpanded = expandedRowIndex === i;
                            const originalRow = results[i];
                            return (
                                <Fragment key={`row-${i}`}>
                                    <tr
                                        onClick={() => onRowExpand(i)}
                                        style={{
                                            borderBottom: isExpanded ? 'none' : '1px solid var(--glass-border)',
                                            cursor: 'pointer',
                                            background: isExpanded ? 'var(--primary-light)' : undefined,
                                            transition: 'background 0.15s ease',
                                        }}
                                        onMouseEnter={(e) => { if (!isExpanded) (e.currentTarget as HTMLElement).style.background = 'var(--bg-page)'; }}
                                        onMouseLeave={(e) => { if (!isExpanded) (e.currentTarget as HTMLElement).style.background = ''; }}
                                    >
                                        <td style={{ padding: '0.4rem', textAlign: 'center', color: 'var(--primary)', fontSize: '0.7rem' }}>
                                            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                        </td>
                                        {columns?.map(key => (
                                            <td key={key} style={{
                                                padding: '0.4rem 0.6rem', maxWidth: '200px',
                                                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                                            }}>
                                                {renderCellValue(row[key])}
                                            </td>
                                        ))}
                                    </tr>
                                    {isExpanded && renderExpandedRow(originalRow)}
                                </Fragment>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}