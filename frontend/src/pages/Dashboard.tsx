import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { Plus, Trash2, Database, RefreshCw, GitMerge, Unlink } from 'lucide-react';
import dredge from '../assets/dredge.png';

const PADDING = 4;

const Dashboard = () => {
    const { currentBucket, setBucket, refreshBuckets, buckets, mergedBuckets, bucketCounts, mergeBuckets, unmergeBucket } = useAuth();
    const [newBucketName, setNewBucketName] = useState('');
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState('');
    // Merge mode: user selects multiple physical buckets to merge
    const [mergeMode, setMergeMode] = useState(false);
    const [mergeSelection, setMergeSelection] = useState<string[]>([]);
    const [merging, setMerging] = useState(false);

    const bucketRefs = useRef<Record<string, HTMLDivElement | null>>({});
    const prevBucketRef = useRef<string | null>(null);
    const [indicator, setIndicator] = useState<{
        left: number;
        top: number;
        width: number;
        height: number;
        useTransition: boolean;
    } | null>(null);

    useEffect(() => {
        refreshBuckets().finally(() => setLoading(false));
    }, []);

    // Traveling active indicator
    useEffect(() => {
        if (!currentBucket) {
            setIndicator(null);
            prevBucketRef.current = currentBucket;
            return;
        }
        const currEl = bucketRefs.current[currentBucket];
        const currRect = currEl?.getBoundingClientRect();
        const prev = prevBucketRef.current;
        const prevEl = prev ? bucketRefs.current[prev] : null;
        const prevRect = prevEl?.getBoundingClientRect();

        if (prev && prev !== currentBucket && prevRect && currRect) {
            setIndicator({
                left: prevRect.left - PADDING,
                top: prevRect.top - PADDING,
                width: prevRect.width + PADDING * 2,
                height: prevRect.height + PADDING * 2,
                useTransition: false,
            });
            const raf = requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    const r = bucketRefs.current[currentBucket]?.getBoundingClientRect();
                    if (r)
                        setIndicator({
                            left: r.left - PADDING,
                            top: r.top - PADDING,
                            width: r.width + PADDING * 2,
                            height: r.height + PADDING * 2,
                            useTransition: true,
                        });
                });
            });
            prevBucketRef.current = currentBucket;
            return () => cancelAnimationFrame(raf);
        }

        const applyCurrent = () => {
            const el = bucketRefs.current[currentBucket];
            const r = el?.getBoundingClientRect();
            if (r)
                setIndicator({
                    left: r.left - PADDING,
                    top: r.top - PADDING,
                    width: r.width + PADDING * 2,
                    height: r.height + PADDING * 2,
                    useTransition: false,
                });
        };
        const raf = requestAnimationFrame(() => {
            requestAnimationFrame(applyCurrent);
        });
        prevBucketRef.current = currentBucket;
        return () => cancelAnimationFrame(raf);
    }, [currentBucket, buckets, mergedBuckets, loading]);

    useEffect(() => {
        if (!currentBucket) return;
        const sync = () => {
            const el = bucketRefs.current[currentBucket];
            const r = el?.getBoundingClientRect();
            if (r)
                setIndicator({
                    left: r.left - PADDING,
                    top: r.top - PADDING,
                    width: r.width + PADDING * 2,
                    height: r.height + PADDING * 2,
                    useTransition: false,
                });
        };
        window.addEventListener('scroll', sync, true);
        window.addEventListener('resize', sync);
        return () => {
            window.removeEventListener('scroll', sync, true);
            window.removeEventListener('resize', sync);
        };
    }, [currentBucket]);

    const handleCreateBucket = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newBucketName.trim()) return;
        setCreating(true);
        setError('');
        try {
            const api = (await import('../api/client')).default;
            await api.post('/auth/buckets', { bucket_name: newBucketName.trim() });
            setNewBucketName('');
            await refreshBuckets();
            setBucket(newBucketName.trim());
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to create bucket');
        } finally {
            setCreating(false);
        }
    };

    const handleDeleteBucket = async (bucketName: string) => {
        if (!window.confirm(`Delete bucket "${bucketName}" and all its data? This cannot be undone.`)) return;
        try {
            const api = (await import('../api/client')).default;
            await api.delete(`/auth/buckets/${encodeURIComponent(bucketName)}`);
            if (currentBucket === bucketName) setBucket('');
            await refreshBuckets();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to delete bucket');
        }
    };

    const handleConfirmMerge = async () => {
        if (mergeSelection.length < 2) return;
        setMerging(true);
        setError('');
        try {
            await mergeBuckets(mergeSelection);
            setMergeMode(false);
            setMergeSelection([]);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to merge buckets');
        } finally {
            setMerging(false);
        }
    };

    const toggleMergeSelect = (b: string) => {
        setMergeSelection(prev =>
            prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b]
        );
    };

    const handleRefresh = async () => {
        setLoading(true);
        await refreshBuckets();
        setLoading(false);
    };

    // Compute merged bucket combined counts
    const getMergedCount = (mergedName: string) => {
        return mergedName.split('+').reduce((sum, b) => sum + (bucketCounts[b] ?? 0), 0);
    };

    const allDisplayBuckets = [...buckets, ...mergedBuckets];

    return (
        <div style={{ position: 'relative', minHeight: '100%' }}>
            <div
                aria-hidden="true"
                style={{
                    position: 'absolute',
                    inset: 0,
                    zIndex: 0,
                    scale: '1.5',
                    backgroundImage: `linear-gradient(to bottom, rgba(248, 250, 252, 0.92) 0%, rgba(241, 245, 249, 0.88) 50%, rgba(248, 250, 252, 0.92) 100%), url(${dredge})`,
                    backgroundPosition: 'center',
                    backgroundRepeat: 'no-repeat',
                    pointerEvents: 'none',
                }}
            />
            <div className="animate-fade-in" style={{ position: 'relative', zIndex: 1 }}>
                {indicator && (
                    <div
                        className="dashboard-active-indicator"
                        style={{
                            left: indicator.left,
                            top: indicator.top,
                            width: indicator.width,
                            height: indicator.height,
                            transition: indicator.useTransition
                                ? 'left 0.6s cubic-bezier(0.4, 0, 0.2, 1), top 0.6s cubic-bezier(0.4, 0, 0.2, 1), width 0.6s cubic-bezier(0.4, 0, 0.2, 1), height 0.6s cubic-bezier(0.4, 0, 0.2, 1)'
                                : 'none',
                        }}
                        aria-hidden
                    />
                )}
                <h1 className="page-title">Dashboard</h1>
                <p className="page-subtitle">Manage your data buckets (collections)</p>

                {error && (
                    <div
                        className="dashboard-section-reveal"
                        style={{
                            background: 'rgba(220, 38, 38, 0.08)',
                            color: 'var(--danger)',
                            padding: '0.75rem 1rem',
                            borderRadius: '8px',
                            border: '1px solid rgba(220, 38, 38, 0.25)',
                            marginBottom: '1.5rem',
                            fontSize: '0.875rem',
                        }}
                    >
                        {error}
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '2rem' }}>
                    {/* Create Bucket Panel */}
                    <div
                        className="glass-panel dashboard-section-reveal"
                        style={{ padding: '2rem', animationDelay: '0.05s', animationFillMode: 'both', height: '300px' }}
                    >
                        <h2
                            style={{
                                fontSize: '1.15rem',
                                marginBottom: '1.5rem',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.5rem',
                                color: 'var(--primary)',
                            }}
                        >
                            <Database size={20} />
                            Create Bucket
                        </h2>
                        <form onSubmit={handleCreateBucket}>
                            <div className="form-group">
                                <label>Bucket Name</label>
                                <input
                                    type="text"
                                    className="input-field"
                                    value={newBucketName}
                                    onChange={(e) => setNewBucketName(e.target.value)}
                                    placeholder="e.g. invoices_q1"
                                    required
                                />
                            </div>
                            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={creating}>
                                <Plus size={18} />
                                {creating ? 'Creating...' : 'Create Bucket'}
                            </button>
                        </form>
                    </div>

                    {/* Buckets List Panel */}
                    <div
                        className="glass-panel dashboard-section-reveal"
                        style={{ padding: '2rem', animationDelay: '0.1s', animationFillMode: 'both', position: 'relative' }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h2 style={{ fontSize: '1.15rem' }}>Your Buckets</h2>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                {mergeMode ? (
                                    <>
                                        <button
                                            className="btn btn-primary"
                                            onClick={handleConfirmMerge}
                                            disabled={mergeSelection.length < 2 || merging}
                                            style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}
                                        >
                                            <GitMerge size={14} />
                                            {merging ? 'Merging...' : `Merge (${mergeSelection.length})`}
                                        </button>
                                        <button
                                            className="btn btn-secondary"
                                            onClick={() => { setMergeMode(false); setMergeSelection([]); }}
                                            style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}
                                        >
                                            Cancel
                                        </button>
                                    </>
                                ) : (
                                    <>
                                        <button
                                            className="btn btn-secondary"
                                            onClick={() => setMergeMode(true)}
                                            style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}
                                            title="Merge buckets"
                                        >
                                            <GitMerge size={14} />
                                        </button>
                                        <button
                                            className="btn btn-secondary"
                                            onClick={handleRefresh}
                                            style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}
                                        >
                                            <RefreshCw size={14} />
                                        </button>
                                    </>
                                )}
                            </div>
                        </div>

                        {mergeMode && (
                            <div style={{
                                padding: '0.6rem 1rem', marginBottom: '1rem',
                                background: 'var(--primary-light)', borderRadius: '8px',
                                border: '1px solid rgba(13,148,136,0.2)', fontSize: '0.82rem',
                                color: 'var(--primary)',
                            }}>
                                Select 2+ buckets to merge, then click <b>Merge</b>.
                            </div>
                        )}

                        {loading ? (
                            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
                                <div
                                    style={{
                                        width: 24,
                                        height: 24,
                                        border: '2px solid var(--glass-border)',
                                        borderTopColor: 'var(--primary)',
                                        borderRadius: '50%',
                                        animation: 'spin 0.8s linear infinite',
                                        margin: '0 auto 1rem',
                                    }}
                                />
                                Loading buckets...
                            </div>
                        ) : allDisplayBuckets.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
                                <Database size={48} style={{ opacity: 0.15, margin: '0 auto 1rem', display: 'block' }} />
                                <p>No buckets yet. Create one to get started.</p>
                            </div>
                        ) : (
                            <div
                                style={{
                                    display: 'grid',
                                    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                                    gap: '1rem',
                                }}
                            >
                                {/* Physical buckets */}
                                {buckets.map((b, index) => {
                                    const count = bucketCounts[b] ?? 0;
                                    const isActive = currentBucket === b;
                                    const isSelected = mergeSelection.includes(b);
                                    return (
                                        <div
                                            key={b}
                                            ref={(el) => { bucketRefs.current[b] = el; }}
                                            className={isActive ? '' : 'dashboard-card-reveal'}
                                            onClick={mergeMode ? () => toggleMergeSelect(b) : undefined}
                                            style={{
                                                ...(isActive || mergeMode ? {} : {
                                                    animationDelay: `${0.15 + index * 0.06}s`,
                                                    animationFillMode: 'both',
                                                }),
                                                position: 'relative',
                                                display: 'flex',
                                                flexDirection: 'column',
                                                alignItems: 'stretch',
                                                padding: '1rem 1.1rem',
                                                background: isActive ? 'transparent' : 'var(--bg-card)',
                                                border: isSelected
                                                    ? '2px solid var(--primary)'
                                                    : isActive
                                                        ? '1px solid transparent'
                                                        : '1px solid var(--glass-border)',
                                                borderRadius: '12px',
                                                transition: 'background 0.25s ease, border-color 0.25s ease',
                                                minHeight: '100px',
                                                cursor: mergeMode ? 'pointer' : undefined,
                                            }}
                                        >
                                            {/* Count badge above name */}
                                            <div style={{
                                                fontSize: '0.7rem', fontWeight: 600,
                                                color: 'var(--text-secondary)',
                                                marginBottom: '0.25rem',
                                                letterSpacing: '0.02em',
                                            }}>
                                                {count.toLocaleString()} records
                                            </div>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                                                <div
                                                    style={{
                                                        width: 40,
                                                        height: 40,
                                                        borderRadius: '10px',
                                                        background: isSelected
                                                            ? 'var(--primary)'
                                                            : isActive
                                                                ? 'var(--primary)'
                                                                : 'var(--primary-light)',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        justifyContent: 'center',
                                                        flexShrink: 0,
                                                    }}
                                                >
                                                    <Database
                                                        size={20}
                                                        style={{ color: (isActive || isSelected) ? 'white' : 'var(--primary)' }}
                                                    />
                                                </div>
                                                <span style={{ fontWeight: 600, fontSize: '0.95rem', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                    {b}
                                                </span>
                                            </div>
                                            {!mergeMode && (
                                                <div style={{ display: 'flex', gap: '0.5rem', marginTop: 'auto', flexWrap: 'wrap' }}>
                                                    {isActive ? (
                                                        <span
                                                            style={{
                                                                fontSize: '0.7rem',
                                                                background: 'var(--primary)',
                                                                color: 'white',
                                                                padding: '0.45rem 0.85rem',
                                                                borderRadius: '8px',
                                                                fontWeight: 600,
                                                                letterSpacing: '0.04em',
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                flex: 1,
                                                                minWidth: 0,
                                                                justifyContent: 'center',
                                                            }}
                                                        >
                                                            ACTIVE
                                                        </span>
                                                    ) : (
                                                        <button
                                                            className="btn btn-secondary"
                                                            style={{ padding: '0.45rem 0.85rem', fontSize: '0.8rem', flex: 1, minWidth: 0 }}
                                                            onClick={() => setBucket(b)}
                                                        >
                                                            Set Active
                                                        </button>
                                                    )}
                                                    <button
                                                        className="btn btn-danger"
                                                        style={{ padding: '0.45rem 0.6rem' }}
                                                        onClick={() => handleDeleteBucket(b)}
                                                        title="Delete"
                                                    >
                                                        <Trash2 size={15} />
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}

                                {/* Merged (virtual) buckets */}
                                {!mergeMode && mergedBuckets.map((m, index) => {
                                    const combinedCount = getMergedCount(m);
                                    const isActive = currentBucket === m;
                                    return (
                                        <div
                                            key={m}
                                            ref={(el) => { bucketRefs.current[m] = el; }}
                                            className={isActive ? '' : 'dashboard-card-reveal'}
                                            style={{
                                                ...(isActive ? {} : {
                                                    animationDelay: `${0.15 + (buckets.length + index) * 0.06}s`,
                                                    animationFillMode: 'both',
                                                }),
                                                position: 'relative',
                                                display: 'flex',
                                                flexDirection: 'column',
                                                alignItems: 'stretch',
                                                padding: '1rem 1.1rem',
                                                background: isActive ? 'transparent' : 'var(--bg-card)',
                                                border: isActive ? '1px solid transparent' : '1px solid rgba(13,148,136,0.35)',
                                                borderRadius: '12px',
                                                transition: 'background 0.25s ease, border-color 0.25s ease',
                                                minHeight: '100px',
                                            }}
                                        >
                                            {/* Combined count */}
                                            <div style={{
                                                fontSize: '0.7rem', fontWeight: 600,
                                                color: 'var(--text-secondary)',
                                                marginBottom: '0.25rem',
                                                letterSpacing: '0.02em',
                                            }}>
                                                {combinedCount.toLocaleString()} records
                                            </div>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                                                <div
                                                    style={{
                                                        width: 40,
                                                        height: 40,
                                                        borderRadius: '10px',
                                                        background: isActive ? 'var(--primary)' : 'rgba(13,148,136,0.12)',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        justifyContent: 'center',
                                                        flexShrink: 0,
                                                    }}
                                                >
                                                    <GitMerge
                                                        size={20}
                                                        style={{ color: isActive ? 'white' : 'var(--primary)' }}
                                                    />
                                                </div>
                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                    <span style={{ fontWeight: 600, fontSize: '0.95rem', overflow: 'hidden', textOverflow: 'ellipsis', display: 'block' }}>
                                                        {m}
                                                    </span>
                                                    <span style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>merged</span>
                                                </div>
                                            </div>
                                            <div style={{ display: 'flex', gap: '0.5rem', marginTop: 'auto', flexWrap: 'wrap' }}>
                                                {isActive ? (
                                                    <span
                                                        style={{
                                                            fontSize: '0.7rem',
                                                            background: 'var(--primary)',
                                                            color: 'white',
                                                            padding: '0.45rem 0.85rem',
                                                            borderRadius: '8px',
                                                            fontWeight: 600,
                                                            letterSpacing: '0.04em',
                                                            display: 'inline-flex',
                                                            alignItems: 'center',
                                                            flex: 1,
                                                            minWidth: 0,
                                                            justifyContent: 'center',
                                                        }}
                                                    >
                                                        ACTIVE
                                                    </span>
                                                ) : (
                                                    <button
                                                        className="btn btn-secondary"
                                                        style={{ padding: '0.45rem 0.85rem', fontSize: '0.8rem', flex: 1, minWidth: 0 }}
                                                        onClick={() => setBucket(m)}
                                                    >
                                                        Set Active
                                                    </button>
                                                )}
                                                <button
                                                    className="btn btn-secondary"
                                                    style={{ padding: '0.45rem 0.6rem' }}
                                                    onClick={() => unmergeBucket(m)}
                                                    title="Unmerge"
                                                >
                                                    <Unlink size={15} />
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>

                <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
            </div>
        </div>
    );
};

export default Dashboard;
