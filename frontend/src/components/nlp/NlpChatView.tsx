import { type FormEvent, type RefObject } from 'react';
import { Send, Bot, User, RefreshCw, Brain, Zap } from 'lucide-react';
import { NlpResultsTable } from './NlpResultsTable';

export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    query?: unknown;
    results?: unknown[];
    totalCount?: number | null;
    queryType?: 'simple' | 'analytical';
    analysis?: string;
    table?: { columns: string[]; rows: string[][] };
    methodology?: string;
    jobId?: string;
    status?: 'complete' | 'processing' | 'error';
    error?: boolean;
}

export interface NlpChatViewProps {
    currentBucket: string;
    messages: ChatMessage[];
    loading: boolean;
    input: string;
    onInputChange: (v: string) => void;
    onSubmit: (e: FormEvent) => void;
    schema: Record<string, unknown> | null;
    schemaOpen: boolean;
    setSchemaOpen: (v: boolean) => void;
    loadSchema: () => void;
    onRefreshSchema: () => void;
    refreshingSchema: boolean;
    expandedRows: Record<string, number | null>;
    onRowExpand: (msgId: string, rowIdx: number) => void;
    messagesEndRef: RefObject<HTMLDivElement | null>;
}

function AnalyticalTable({ table }: { table: { columns: string[]; rows: string[][] } }) {
    if (!table || !table.columns || table.columns.length === 0) return null;
    return (
        <div style={{ overflowX: 'auto', maxHeight: '500px', overflowY: 'auto', borderRadius: '8px', border: '1px solid var(--glass-border)', marginTop: '0.75rem' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem', fontFamily: "'Consolas', monospace" }}>
                <thead>
                    <tr>
                        {table.columns.map(col => (
                            <th key={col} style={{
                                padding: '0.5rem 0.6rem', background: 'var(--bg-card)', color: 'var(--primary)',
                                fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase',
                                letterSpacing: '0.04em', textAlign: 'left', whiteSpace: 'nowrap',
                                borderBottom: '2px solid var(--primary)', position: 'sticky', top: 0, zIndex: 1,
                            }}>{col}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {table.rows.map((row, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--glass-border)' }}
                            onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--bg-page)'}
                            onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}>
                            {row.map((cell, j) => (
                                <td key={j} style={{
                                    padding: '0.4rem 0.6rem', maxWidth: '300px',
                                    overflow: 'hidden', textOverflow: 'ellipsis',
                                }}>{cell}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function AnalyticalResponse({ msg }: { msg: ChatMessage }) {
    return (
        <div>
            {msg.analysis && (
                <div style={{ marginBottom: '0.75rem' }}>
                    <span style={{
                        fontSize: '0.75rem', fontWeight: 600, color: '#a855f7',
                        textTransform: 'uppercase', letterSpacing: '0.04em',
                        display: 'flex', alignItems: 'center', gap: '0.35rem',
                    }}>
                        <Brain size={14} /> Analysis
                    </span>
                    <p style={{
                        margin: '0.5rem 0 0', fontSize: '0.85rem', lineHeight: 1.6,
                        color: 'var(--text-primary)',
                    }}>
                        {msg.analysis}
                    </p>
                </div>
            )}

            {msg.table && msg.table.columns && msg.table.columns.length > 0 && (
                <AnalyticalTable table={msg.table} />
            )}

            {msg.methodology && (
                <details style={{ marginTop: '0.75rem' }}>
                    <summary style={{
                        cursor: 'pointer', fontSize: '0.72rem', color: 'var(--text-secondary)',
                        fontStyle: 'italic',
                    }}>
                        Methodology
                    </summary>
                    <p style={{
                        margin: '0.35rem 0 0', fontSize: '0.75rem', color: 'var(--text-secondary)',
                        lineHeight: 1.5, paddingLeft: '0.5rem',
                        borderLeft: '2px solid var(--glass-border)',
                    }}>
                        {msg.methodology}
                    </p>
                </details>
            )}
        </div>
    );
}

function ProcessingIndicator() {
    return (
        <div style={{
            display: 'flex', alignItems: 'center', gap: '0.75rem',
            padding: '0.75rem', borderRadius: '8px',
            background: 'rgba(168, 85, 247, 0.05)',
            border: '1px solid rgba(168, 85, 247, 0.15)',
        }}>
            <div style={{
                width: 18, height: 18, border: '2px solid rgba(168,85,247,0.2)',
                borderTopColor: '#a855f7', borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
            }} />
            <div>
                <span style={{ color: '#a855f7', fontSize: '0.85rem', fontWeight: 500 }}>
                    Analyzing your data...
                </span>
                <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    Running multi-step analysis. You can navigate away — results will be saved.
                </p>
            </div>
        </div>
    );
}

function SimpleResponse({ msg, expandedRows, onRowExpand }: {
    msg: ChatMessage;
    expandedRows: Record<string, number | null>;
    onRowExpand: (msgId: string, rowIdx: number) => void;
}) {
    return (
        <div>
            {msg.query != null && (
                <div style={{ marginBottom: '1rem' }}>
                    <span style={{
                        fontSize: '0.75rem', fontWeight: 600, color: 'var(--primary)',
                        textTransform: 'uppercase', letterSpacing: '0.04em',
                        display: 'flex', alignItems: 'center', gap: '0.35rem',
                    }}>
                        <Zap size={14} /> Generated Query
                    </span>
                    <pre style={{
                        margin: '0.5rem 0 0', padding: '0.75rem', borderRadius: '8px',
                        background: 'var(--bg-page)', fontSize: '0.8rem',
                        fontFamily: "'Consolas', monospace", color: 'var(--success)',
                        whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                        border: '1px solid var(--glass-border)',
                    }}>
                        {JSON.stringify(msg.query as object, null, 2)}
                    </pre>
                </div>
            )}

            {msg.results && msg.results.length > 0 ? (
                <NlpResultsTable
                    results={msg.results}
                    msgId={msg.id}
                    expandedRowIndex={expandedRows[msg.id] ?? null}
                    onRowExpand={(idx) => onRowExpand(msg.id, idx)}
                />
            ) : msg.results ? (
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', margin: 0 }}>No results found.</p>
            ) : null}
        </div>
    );
}

export function NlpChatView({
    currentBucket,
    messages,
    loading,
    input,
    onInputChange,
    onSubmit,
    schema,
    schemaOpen,
    setSchemaOpen,
    loadSchema,
    onRefreshSchema,
    refreshingSchema,
    expandedRows,
    onRowExpand,
    messagesEndRef,
}: NlpChatViewProps) {
    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* Header */}
            <div style={{ padding: '0.75rem 1rem 0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 className="page-title" style={{ margin: 0, fontSize: '1.25rem' }}>NLP Query</h1>
                    <p style={{ margin: '0.15rem 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        Querying <b style={{ color: 'var(--primary)' }}>{currentBucket}</b>
                    </p>
                </div>
                <button
                    className="btn btn-secondary"
                    disabled={refreshingSchema}
                    onClick={onRefreshSchema}
                    style={{ padding: '0.4rem 0.6rem', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                >
                    <RefreshCw size={13} style={refreshingSchema ? { animation: 'spin 0.8s linear infinite' } : undefined} /> Refresh Schema
                </button>
            </div>

            {/* Schema Panel */}
            {schema != null && Object.keys(schema).length > 0 && (
                <div style={{
                    margin: '0 0.75rem 0.5rem', background: 'var(--bg-card)',
                    border: '1px solid var(--glass-border)', borderRadius: '10px', overflow: 'hidden',
                }}>
                    <div
                        onClick={() => setSchemaOpen(!schemaOpen)}
                        style={{
                            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                            padding: '0.5rem 0.75rem', cursor: 'pointer', background: 'rgba(15,23,42,0.04)',
                            borderBottom: schemaOpen ? '1px solid var(--glass-border)' : 'none',
                        }}
                    >
                        <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--success)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            Schema Context
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <button className="btn btn-secondary" onClick={e => { e.stopPropagation(); loadSchema(); }} style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem', border: 'none' }}>
                                <RefreshCw size={11} />
                            </button>
                            <span style={{ color: 'var(--text-secondary)', fontSize: '0.7rem' }}>{schemaOpen ? '\u25BC' : '\u25B6'}</span>
                        </div>
                    </div>
                    {schemaOpen && (
                        <div style={{ padding: '0.5rem 0.75rem', maxHeight: '180px', overflowY: 'auto' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '0.4rem' }}>
                                {Object.entries(schema as Record<string, { type?: string }>).map(([field, info]) => (
                                    <div key={field} style={{
                                        display: 'flex', alignItems: 'baseline', gap: '0.4rem',
                                        padding: '0.3rem 0.5rem', background: 'rgba(15,23,42,0.05)', borderRadius: '5px', fontSize: '0.72rem',
                                    }}>
                                        <span style={{ fontWeight: 600, fontFamily: "'Consolas', monospace", color: 'var(--text-primary)' }}>{field}</span>
                                        <span style={{ color: 'var(--primary)', fontWeight: 500, fontSize: '0.65rem' }}>{(info as { type?: string })?.type ?? 'unknown'}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Chat Messages */}
            <div className="glass-panel nlp-chat-area" style={{
                flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden',
                border: '1px solid var(--glass-border)', margin: '0 0.75rem',
                borderRadius: '10px',
            }}>
                <div className="nlp-chat-messages-wrapper">
                    <div className="nlp-chat-bg" aria-hidden="true" />
                    <div className="nlp-chat-messages-scroll" style={{
                        flex: 1, overflowY: 'auto', padding: '1.25rem',
                        display: 'flex', flexDirection: 'column', gap: '1.25rem',
                    }}>
                        {messages.length === 0 ? (
                            <div style={{ margin: 'auto', textAlign: 'center', color: 'var(--text-secondary)' }}>
                                <Bot size={48} style={{ opacity: 0.15, margin: '0 auto 1rem', display: 'block' }} />
                                <h3 style={{ fontWeight: 500, marginBottom: '0.5rem' }}>Ask anything about your data</h3>
                                <p style={{ fontSize: '0.82rem', maxWidth: '450px', margin: '0 auto', lineHeight: 1.6 }}>
                                    <b>Simple queries:</b> "Show all records where amount {'>'} 1000"<br />
                                    <b>Analytical queries:</b> "Which users likely support democrats?"
                                </p>
                            </div>
                        ) : (
                            messages.map(msg => (
                                <div key={msg.id} style={{
                                    display: 'flex', gap: '0.75rem',
                                    alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                                    maxWidth: msg.role === 'assistant' ? '92%' : '70%',
                                }}>
                                    {msg.role === 'assistant' && (
                                        <div style={{
                                            width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                                            background: msg.error
                                                ? 'var(--danger)'
                                                : msg.queryType === 'analytical'
                                                    ? 'linear-gradient(135deg, #a855f7, #6366f1)'
                                                    : 'linear-gradient(135deg, #0d9488, #38bdf8)',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        }}>
                                            {msg.queryType === 'analytical'
                                                ? <Brain size={14} color="white" />
                                                : <Bot size={14} color="white" />}
                                        </div>
                                    )}

                                    <div style={{
                                        background: msg.role === 'user' ? 'var(--primary-light)' : 'var(--bg-card)',
                                        border: `1px solid ${msg.role === 'user'
                                            ? 'rgba(13, 148, 136, 0.3)'
                                            : msg.error
                                                ? 'rgba(220, 38, 38, 0.3)'
                                                : msg.queryType === 'analytical'
                                                    ? 'rgba(168, 85, 247, 0.15)'
                                                    : 'var(--glass-border)'}`,
                                        padding: '0.85rem', borderRadius: '12px',
                                        borderTopRightRadius: msg.role === 'user' ? 0 : '12px',
                                        borderTopLeftRadius: msg.role === 'assistant' ? 0 : '12px',
                                        width: '100%',
                                    }}>
                                        {msg.role === 'user' ? (
                                            <p style={{ margin: 0, color: 'var(--text-primary)' }}>{msg.content}</p>
                                        ) : msg.error ? (
                                            <p style={{ margin: 0, color: 'var(--danger)' }}>{msg.content}</p>
                                        ) : msg.status === 'processing' ? (
                                            <ProcessingIndicator />
                                        ) : msg.queryType === 'analytical' ? (
                                            <AnalyticalResponse msg={msg} />
                                        ) : (
                                            <SimpleResponse
                                                msg={msg}
                                                expandedRows={expandedRows}
                                                onRowExpand={onRowExpand}
                                            />
                                        )}
                                    </div>

                                    {msg.role === 'user' && (
                                        <div style={{
                                            width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                                            background: 'var(--primary-light)',
                                            border: '1px solid rgba(13, 148, 136, 0.25)',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        }}>
                                            <User size={14} style={{ color: 'var(--primary)' }} />
                                        </div>
                                    )}
                                </div>
                            ))
                        )}

                        {loading && (
                            <div style={{ display: 'flex', gap: '0.75rem', alignSelf: 'flex-start' }}>
                                <div style={{
                                    width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                                    background: 'linear-gradient(135deg, #0d9488, #38bdf8)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <Bot size={14} color="white" />
                                </div>
                                <div style={{
                                    background: 'var(--bg-card)', border: '1px solid var(--glass-border)',
                                    padding: '0.85rem', borderRadius: '12px', borderTopLeftRadius: 0,
                                    display: 'flex', alignItems: 'center', gap: '0.75rem',
                                }}>
                                    <div style={{
                                        width: 16, height: 16, border: '2px solid var(--glass-border)',
                                        borderTopColor: 'var(--primary)', borderRadius: '50%',
                                        animation: 'spin 0.8s linear infinite',
                                    }} />
                                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                                        Classifying and processing...
                                    </span>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>
                </div>

                {/* Input Bar */}
                <div style={{ padding: '0.75rem 1rem', borderTop: '1px solid var(--glass-border)', background: 'var(--bg-card)' }}>
                    <form onSubmit={onSubmit} style={{ position: 'relative' }}>
                        <input
                            type="text"
                            value={input}
                            onChange={e => onInputChange(e.target.value)}
                            placeholder="Ask a question about your data..."
                            className="input-field"
                            style={{ paddingRight: '3.5rem', padding: '0.8rem 3.5rem 0.8rem 1.1rem', borderRadius: '20px' }}
                            disabled={loading}
                        />
                        <button
                            type="submit"
                            className="btn btn-primary"
                            style={{
                                position: 'absolute', right: '0.35rem', top: '50%', transform: 'translateY(-50%)',
                                padding: '0.45rem', borderRadius: '50%', width: 34, height: 34,
                            }}
                            disabled={loading || !input.trim()}
                        >
                            <Send size={15} />
                        </button>
                    </form>
                </div>
            </div>
            <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
        </div>
    );
}
