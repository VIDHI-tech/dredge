import { useState, useRef, useEffect, useCallback, type FormEvent } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { MessageSquare, Plus, Trash2, Pencil, Check, X } from 'lucide-react';
import { NlpChatView, type ChatMessage } from '../components/nlp/NlpChatView';

interface ConversationSummary {
    id: string;
    title: string;
    collection: string;
    created_at: string;
    updated_at: string;
    message_count: number;
}

const NlpQuery = () => {
    const { currentBucket } = useAuth();

    // Conversation list state
    const [conversations, setConversations] = useState<ConversationSummary[]>([]);
    const [activeConvoId, setActiveConvoId] = useState<string | null>(null);
    const [loadingConvos, setLoadingConvos] = useState(false);

    // Rename state
    const [renamingId, setRenamingId] = useState<string | null>(null);
    const [renameText, setRenameText] = useState('');

    // Chat state
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
    const [schemaOpen, setSchemaOpen] = useState(false);
    const [refreshingSchema, setRefreshingSchema] = useState(false);
    const [expandedRows, setExpandedRows] = useState<Record<string, number | null>>({});
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Job polling refs
    const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        if (currentBucket) {
            loadConversations();
            loadSchema();
        }
        return () => {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        };
    }, [currentBucket]);

    // ---- Conversation management ----

    const loadConversations = async () => {
        if (!currentBucket) return;
        setLoadingConvos(true);
        try {
            const res = await api.get('/query/conversations');
            setConversations(res.data.conversations || []);
        } catch {
            setConversations([]);
        } finally {
            setLoadingConvos(false);
        }
    };

    const loadConversation = async (convoId: string) => {
        try {
            const res = await api.get(`/query/conversations/${convoId}`);
            const msgs: ChatMessage[] = (res.data.messages || []).map((m: any) => ({
                id: m.id,
                role: m.role,
                content: m.content,
                query: m.mongo_query,
                results: m.results,
                totalCount: m.total_count,
                queryType: m.query_type,
                analysis: m.analysis,
                table: m.table,
                methodology: m.methodology,
                jobId: m.job_id,
                status: m.status || 'complete',
                error: m.status === 'error',
            }));
            setMessages(msgs);
            setActiveConvoId(convoId);
            setExpandedRows({});

            // Check for any processing messages and poll them
            const processingMsgs = msgs.filter(m => m.status === 'processing' && m.jobId);
            for (const msg of processingMsgs) {
                startPolling(msg.jobId!, msg.id);
            }
        } catch {
            // ignore
        }
    };

    const startNewChat = () => {
        setActiveConvoId(null);
        setMessages([]);
        setExpandedRows({});
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    };

    const deleteConversation = async (convoId: string) => {
        try {
            await api.delete(`/query/conversations/${convoId}`);
            if (activeConvoId === convoId) startNewChat();
            setConversations(prev => prev.filter(c => c.id !== convoId));
        } catch { /* ignore */ }
    };

    const startRename = (convo: ConversationSummary) => {
        setRenamingId(convo.id);
        setRenameText(convo.title);
    };

    const confirmRename = async () => {
        if (!renamingId || !renameText.trim()) return;
        try {
            await api.patch(`/query/conversations/${renamingId}`, { title: renameText.trim() });
            setConversations(prev =>
                prev.map(c => c.id === renamingId ? { ...c, title: renameText.trim() } : c)
            );
        } catch { /* ignore */ }
        setRenamingId(null);
    };

    // ---- Schema ----

    const loadSchema = async () => {
        if (!currentBucket) return;
        try {
            const res = await api.get(`/nlp/schema/${encodeURIComponent(currentBucket)}`);
            setSchema((res.data.schema || res.data) as Record<string, unknown>);
        } catch {
            setSchema(null);
        }
    };

    const handleRefreshSchema = async () => {
        if (!currentBucket) return;
        setRefreshingSchema(true);
        try {
            await api.post('/nlp/refresh-schema', { collection: currentBucket });
            await loadSchema();
        } catch { /* ignore */ }
        finally { setRefreshingSchema(false); }
    };

    // ---- Row expansion ----

    const toggleRowExpand = (msgId: string, rowIdx: number) => {
        setExpandedRows(prev => ({
            ...prev,
            [msgId]: prev[msgId] === rowIdx ? null : rowIdx,
        }));
    };

    // ---- Job polling ----

    const startPolling = useCallback((jobId: string, msgId: string) => {
        // Clear any existing poll
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

        pollIntervalRef.current = setInterval(async () => {
            try {
                const res = await api.get(`/query/job/${jobId}`);
                const { status, analysis, table, methodology, error } = res.data;

                if (status === 'complete') {
                    setMessages(prev => prev.map(m =>
                        m.id === msgId ? {
                            ...m,
                            status: 'complete',
                            analysis,
                            table,
                            methodology,
                        } : m
                    ));
                    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                    // Refresh conversation list to update title
                    loadConversations();
                } else if (status === 'error') {
                    setMessages(prev => prev.map(m =>
                        m.id === msgId ? {
                            ...m,
                            status: 'error',
                            content: error || 'Analysis failed',
                            error: true,
                        } : m
                    ));
                    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
                    pollIntervalRef.current = null;
                }
            } catch {
                // Keep polling on network errors
            }
        }, 3000);
    }, []);

    // ---- Submit ----

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        if (!input.trim() || !currentBucket) return;

        const userMsg: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: input,
            status: 'complete',
        };

        setMessages(prev => [...prev, userMsg]);
        const queryText = input;
        setInput('');
        setLoading(true);

        try {
            const res = await api.post('/query/ask', {
                text: queryText,
                collection: currentBucket,
                conversation_id: activeConvoId || undefined,
            });

            const data = res.data;
            // Update conversation ID if this was a new chat
            if (!activeConvoId && data.conversation_id) {
                setActiveConvoId(data.conversation_id);
                // Reload conversations to show the new one
                setTimeout(() => loadConversations(), 1000);
            }

            if (data.query_type === 'simple') {
                const assistantMsg: ChatMessage = {
                    id: data.message_id || (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: '',
                    query: data.mongo_query,
                    results: data.results || [],
                    totalCount: data.total_count,
                    queryType: 'simple',
                    status: 'complete',
                };
                setMessages(prev => [...prev, assistantMsg]);
            } else {
                // Analytical — show processing message, start polling
                const assistantMsg: ChatMessage = {
                    id: data.message_id || (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: '',
                    queryType: 'analytical',
                    jobId: data.job_id,
                    status: 'processing',
                };
                setMessages(prev => [...prev, assistantMsg]);

                if (data.job_id) {
                    startPolling(data.job_id, assistantMsg.id);
                }
            }
        } catch (err: unknown) {
            const errorMsg: ChatMessage = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to process query.',
                error: true,
                status: 'error',
            };
            setMessages(prev => [...prev, errorMsg]);
        } finally {
            setLoading(false);
        }
    };

    // ---- Group conversations by date ----

    const groupConversations = (convos: ConversationSummary[]) => {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today.getTime() - 86400000);
        const weekAgo = new Date(today.getTime() - 7 * 86400000);

        const groups: { label: string; items: ConversationSummary[] }[] = [
            { label: 'Today', items: [] },
            { label: 'Yesterday', items: [] },
            { label: 'Last 7 Days', items: [] },
            { label: 'Older', items: [] },
        ];

        for (const c of convos) {
            const d = new Date(c.updated_at);
            if (d >= today) groups[0].items.push(c);
            else if (d >= yesterday) groups[1].items.push(c);
            else if (d >= weekAgo) groups[2].items.push(c);
            else groups[3].items.push(c);
        }

        return groups.filter(g => g.items.length > 0);
    };

    // ---- Render ----

    if (!currentBucket) {
        return (
            <div className="animate-fade-in">
                <h1 className="page-title">NLP Query</h1>
                <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', marginTop: '2rem' }}>
                    <MessageSquare size={48} style={{ color: 'var(--text-secondary)', marginBottom: '1rem', opacity: 0.3 }} />
                    <h2 style={{ marginBottom: '0.5rem' }}>No Active Bucket</h2>
                    <p style={{ color: 'var(--text-secondary)' }}>Select a bucket to start querying your data.</p>
                </div>
            </div>
        );
    }

    const groups = groupConversations(conversations);

    return (
        <div className="animate-fade-in" style={{ display: 'flex', height: 'calc(100vh - 4rem)', gap: '0' }}>
            {/* Conversation Sidebar */}
            <div style={{
                width: '260px',
                minWidth: '260px',
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--bg-card)',
                borderRight: '1px solid var(--glass-border)',
                borderRadius: '12px 0 0 12px',
                overflow: 'hidden',
            }}>
                {/* New Chat button */}
                <div style={{ padding: '0.75rem' }}>
                    <button
                        onClick={startNewChat}
                        className="btn btn-primary"
                        style={{
                            width: '100%', display: 'flex', alignItems: 'center',
                            justifyContent: 'center', gap: '0.5rem', padding: '0.6rem',
                            fontSize: '0.85rem', borderRadius: '8px',
                        }}
                    >
                        <Plus size={16} /> New Chat
                    </button>
                </div>

                {/* Conversation list */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '0 0.5rem 0.5rem' }}>
                    {loadingConvos && conversations.length === 0 ? (
                        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                            Loading...
                        </div>
                    ) : conversations.length === 0 ? (
                        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                            No conversations yet
                        </div>
                    ) : (
                        groups.map(group => (
                            <div key={group.label}>
                                <div style={{
                                    padding: '0.5rem 0.5rem 0.25rem',
                                    fontSize: '0.7rem', fontWeight: 600,
                                    color: 'var(--text-secondary)',
                                    textTransform: 'uppercase',
                                    letterSpacing: '0.05em',
                                }}>
                                    {group.label}
                                </div>
                                {group.items.map(convo => (
                                    <div
                                        key={convo.id}
                                        onClick={() => renamingId !== convo.id && loadConversation(convo.id)}
                                        style={{
                                            padding: '0.5rem 0.6rem',
                                            borderRadius: '6px',
                                            cursor: 'pointer',
                                            fontSize: '0.82rem',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'space-between',
                                            gap: '0.25rem',
                                            background: activeConvoId === convo.id ? 'var(--primary-light)' : 'transparent',
                                            border: activeConvoId === convo.id ? '1px solid rgba(13,148,136,0.2)' : '1px solid transparent',
                                            marginBottom: '2px',
                                            transition: 'background 0.15s',
                                        }}
                                        onMouseEnter={e => {
                                            if (activeConvoId !== convo.id)
                                                (e.currentTarget as HTMLElement).style.background = 'rgba(15,23,42,0.06)';
                                        }}
                                        onMouseLeave={e => {
                                            if (activeConvoId !== convo.id)
                                                (e.currentTarget as HTMLElement).style.background = 'transparent';
                                        }}
                                    >
                                        {renamingId === convo.id ? (
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', flex: 1 }}
                                                onClick={e => e.stopPropagation()}>
                                                <input
                                                    value={renameText}
                                                    onChange={e => setRenameText(e.target.value)}
                                                    onKeyDown={e => e.key === 'Enter' && confirmRename()}
                                                    autoFocus
                                                    style={{
                                                        flex: 1, fontSize: '0.8rem', padding: '0.2rem 0.3rem',
                                                        background: 'var(--bg-page)', border: '1px solid var(--glass-border)',
                                                        borderRadius: '4px', color: 'var(--text-primary)',
                                                    }}
                                                />
                                                <button onClick={confirmRename} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'var(--success)' }}>
                                                    <Check size={14} />
                                                </button>
                                                <button onClick={() => setRenamingId(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'var(--text-secondary)' }}>
                                                    <X size={14} />
                                                </button>
                                            </div>
                                        ) : (
                                            <>
                                                <span style={{
                                                    overflow: 'hidden', textOverflow: 'ellipsis',
                                                    whiteSpace: 'nowrap', flex: 1,
                                                    color: activeConvoId === convo.id ? 'var(--primary)' : 'var(--text-primary)',
                                                }}>
                                                    {convo.title}
                                                </span>
                                                <div style={{ display: 'flex', gap: '2px', opacity: 0.5, flexShrink: 0 }}
                                                    className="convo-actions">
                                                    <button
                                                        onClick={e => { e.stopPropagation(); startRename(convo); }}
                                                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'var(--text-secondary)' }}
                                                    >
                                                        <Pencil size={12} />
                                                    </button>
                                                    <button
                                                        onClick={e => { e.stopPropagation(); deleteConversation(convo.id); }}
                                                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'var(--danger)' }}
                                                    >
                                                        <Trash2 size={12} />
                                                    </button>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                ))}
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Chat Area */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <NlpChatView
                    currentBucket={currentBucket}
                    messages={messages}
                    loading={loading}
                    input={input}
                    onInputChange={setInput}
                    onSubmit={handleSubmit}
                    schema={schema}
                    schemaOpen={schemaOpen}
                    setSchemaOpen={setSchemaOpen}
                    loadSchema={loadSchema}
                    onRefreshSchema={handleRefreshSchema}
                    refreshingSchema={refreshingSchema}
                    expandedRows={expandedRows}
                    onRowExpand={toggleRowExpand}
                    messagesEndRef={messagesEndRef}
                />
            </div>
        </div>
    );
};

export default NlpQuery;
