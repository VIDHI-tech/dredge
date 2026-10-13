import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { UploadCloud, FileText, Image as ImageIcon, FileSpreadsheet, CheckCircle2, RefreshCw, Save, Eye } from 'lucide-react';

type UploadTarget = 'pdf' | 'image' | 'csv';

interface ProcessingJob {
    id: string;
    filename: string;
    status: string;
    phase: string;
    percent: number;
    docId?: string;
}

const Ingestion = () => {
    const { currentBucket } = useAuth();
    const [activeTab, setActiveTab] = useState<UploadTarget>('pdf');
    const [files, setFiles] = useState<File[]>([]);
    const [jobs, setJobs] = useState<ProcessingJob[]>([]);
    const [processedDocs, setProcessedDocs] = useState<string[]>([]);
    const [resultData, setResultData] = useState<any[] | null>(null);
    const [resultDocId, setResultDocId] = useState<string | null>(null);
    const [saveStatus, setSaveStatus] = useState<{ msg: string; ok: boolean } | null>(null);
    const [loadingDocs, setLoadingDocs] = useState(false);

    // When currentBucket is merged ("b1+b2"), user picks which physical bucket to save into
    const isMerged = currentBucket?.includes('+') ?? false;
    const physicalBuckets = isMerged ? (currentBucket?.split('+') ?? []) : [];
    const [targetBucket, setTargetBucket] = useState<string>('');

    // Endpoint for CSV is /convert, others are /upload
    const getUploadEndpoint = (tab: UploadTarget) => tab === 'csv' ? `/${tab}/convert` : `/${tab}/upload`;

    // Load processed docs on tab change
    useEffect(() => {
        loadProcessedDocs();
    }, [activeTab, currentBucket]);

    const loadProcessedDocs = async () => {
        if (!currentBucket) return;
        setLoadingDocs(true);
        try {
            const res = await api.get(`/${activeTab}/list-processed`);
            setProcessedDocs(res.data.documents || []);
        } catch {
            setProcessedDocs([]);
        } finally {
            setLoadingDocs(false);
        }
    };

    const handleUpload = async () => {
        if (files.length === 0 || !currentBucket) return;

        const newJobs = files.map((f, i) => ({
            id: `job-${Date.now()}-${i}`,
            filename: f.name,
            status: 'uploading',
            phase: 'Uploading...',
            percent: 0
        }));

        setJobs(prev => [...newJobs, ...prev]);

        const formData = new FormData();
        files.forEach(f => formData.append('files', f));
        setFiles([]);

        try {
            const res = await api.post(getUploadEndpoint(activeTab), formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            const returnedResults = res.data.results || [];

            setJobs(prev => prev.map(job => {
                const resMatch = returnedResults.find((r: any) => r.filename === job.filename);
                if (resMatch) {
                    if (resMatch.status === 'error') {
                        return { ...job, status: 'error', phase: resMatch.detail || 'Error', percent: 0 };
                    }
                    pollStatus(job.id, resMatch.doc_id);
                    return { ...job, status: 'processing', phase: 'Queued', percent: 5, docId: resMatch.doc_id };
                }
                return job;
            }));
        } catch (err: any) {
            setJobs(prev => prev.map(j => newJobs.find(nj => nj.id === j.id) ? { ...j, status: 'error', phase: 'Error', percent: 0 } : j));
        }
    };

    const pollStatus = (jobId: string, docId: string) => {
        const interval = setInterval(async () => {
            try {
                const res = await api.get(`/${activeTab}/status/${docId}`);
                const data = res.data;
                let percent = 0;
                let phase = data.phase || data.status || 'processing';

                if (data.status === 'completed') {
                    percent = 100;
                    phase = 'Done';
                    clearInterval(interval);
                    loadProcessedDocs();
                } else if (phase === 'queued') percent = 5;
                else if (phase === 'inferring_schema') percent = 15;
                else if (phase === 'chunking') percent = 25;
                else if (phase === 'processing') {
                    const total = parseInt(data.total_chunks) || 1;
                    const processed = parseInt(data.processed_chunks) || 0;
                    percent = 25 + ((processed / total) * 65);
                    phase = `Processing ${processed}/${total} chunks`;
                } else if (phase === 'merging') { percent = 95; phase = 'Merging results...'; }
                else if (data.status?.startsWith('error')) {
                    phase = 'Error';
                    clearInterval(interval);
                }

                setJobs(prev => prev.map(j => j.id === jobId ? { ...j, status: data.status, phase, percent, docId } : j));
            } catch {
                clearInterval(interval);
            }
        }, 2000);
    };

    const viewResult = async (docId: string) => {
        setResultDocId(docId);
        setSaveStatus(null);
        try {
            const res = await api.get(`/${activeTab}/result/${docId}`);
            let data = res.data.data || res.data;
            if (Array.isArray(data) && data.length > 0 && Array.isArray(data[0])) data = data.flat();
            if (!Array.isArray(data)) data = [data];
            setResultData(data);
        } catch {
            setResultData([]);
        }
    };

    const saveToMongo = async () => {
        if (!resultDocId || !currentBucket) return;
        // For merged buckets, require the user to pick a target physical bucket
        const bucket = isMerged ? targetBucket : currentBucket;
        if (isMerged && !bucket) {
            setSaveStatus({ msg: 'Select a target bucket before saving.', ok: false });
            return;
        }
        setSaveStatus(null);
        try {
            await api.post(`/${activeTab}/save-to-mongo/${resultDocId}?bucket=${encodeURIComponent(bucket)}`, resultData);
            setSaveStatus({ msg: `Saved to bucket "${bucket}" successfully!`, ok: true });
        } catch (err: any) {
            setSaveStatus({ msg: err.response?.data?.detail || 'Failed to save', ok: false });
        }
    };

    if (!currentBucket) {
        return (
            <div className="animate-fade-in">
                <h1 className="page-title">Ingestion</h1>
                <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', marginTop: '2rem' }}>
                    <UploadCloud size={48} style={{ color: 'var(--text-secondary)', marginBottom: '1rem', opacity: 0.3 }} />
                    <h2 style={{ marginBottom: '0.5rem' }}>No Active Bucket</h2>
                    <p style={{ color: 'var(--text-secondary)' }}>Select or create a bucket in the Dashboard first.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="animate-fade-in">
            <h1 className="page-title">Ingestion</h1>
            <p className="page-subtitle">Upload files into bucket: <b style={{ color: 'var(--primary)' }}>{currentBucket}</b></p>

            {/* Tab Selector */}
            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '2rem' }}>
                {(['pdf', 'image', 'csv'] as UploadTarget[]).map(tab => (
                    <button
                        key={tab}
                        className={`btn ${activeTab === tab ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ flex: 1, textTransform: 'uppercase', fontSize: '0.85rem', letterSpacing: '0.03em' }}
                        onClick={() => { setActiveTab(tab); setFiles([]); setResultData(null); setResultDocId(null); setSaveStatus(null); }}
                    >
                        {tab === 'pdf' ? <FileText size={18} /> : tab === 'image' ? <ImageIcon size={18} /> : <FileSpreadsheet size={18} />}
                        {tab}
                    </button>
                ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                {/* Upload Zone */}
                <div className="glass-panel" style={{ padding: '2rem' }}>
                    <h3 style={{ marginBottom: '1.5rem', fontSize: '1rem' }}>Upload</h3>
                    <div style={{
                        border: '2px dashed var(--glass-border)', borderRadius: '12px', padding: '3rem 1.5rem',
                        textAlign: 'center', background: 'rgba(0,0,0,0.15)', transition: 'all 0.3s', cursor: 'pointer'
                    }}
                        onClick={() => document.getElementById('file-upload')?.click()}
                    >
                        {!files || files.length === 0 ? (
                            <>
                                <UploadCloud size={48} style={{ color: 'var(--text-secondary)', marginBottom: '0.75rem', opacity: 0.5 }} />
                                <p style={{ fontWeight: 500, marginBottom: '0.25rem' }}>Click to select files</p>
                                <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>or drag and drop</p>
                                <input type="file" multiple onChange={(e) => e.target.files && setFiles(Array.from(e.target.files))} style={{ display: 'none' }} id="file-upload" />
                            </>
                        ) : (
                            <>
                                <p style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{files.length} file(s) selected</p>
                                <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginBottom: '1rem', maxHeight: '100px', overflowY: 'auto' }}>
                                    {files.map(f => (
                                        <div key={f.name}>{f.name} ({(f.size / 1024 / 1024).toFixed(2)} MB)</div>
                                    ))}
                                </div>
                                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                                    <button className="btn btn-primary" onClick={(e) => { e.stopPropagation(); handleUpload(); }}>
                                        <UploadCloud size={16} /> Upload All
                                    </button>
                                    <button className="btn btn-secondary" onClick={(e) => { e.stopPropagation(); setFiles([]); }}>Cancel</button>
                                </div>
                                <input type="file" multiple onChange={(e) => e.target.files && setFiles(Array.from(e.target.files))} style={{ display: 'none' }} id="file-upload" />
                            </>
                        )}
                    </div>

                    {/* Active Jobs */}
                    {jobs.length > 0 && (
                        <div style={{ marginTop: '1.5rem' }}>
                            <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>Processing Jobs</h4>
                            {jobs.map(job => (
                                <div key={job.id} style={{
                                    padding: '0.75rem', background: 'rgba(0,0,0,0.2)', borderRadius: '8px',
                                    border: '1px solid var(--glass-border)', marginBottom: '0.5rem'
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                                        <span style={{ fontWeight: 500 }}>{job.filename}</span>
                                        <span style={{ color: job.status === 'completed' ? 'var(--success)' : job.phase === 'Error' ? 'var(--danger)' : 'var(--primary)', fontSize: '0.8rem' }}>
                                            {job.phase}
                                        </span>
                                    </div>
                                    <div style={{ height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3, overflow: 'hidden' }}>
                                        <div style={{
                                            height: '100%',
                                            width: `${job.percent}%`,
                                            background: job.status === 'completed' ? 'var(--success)' : 'var(--primary)',
                                            borderRadius: 3, transition: 'width 0.5s ease'
                                        }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Processed Documents List */}
                <div className="glass-panel" style={{ padding: '2rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                        <h3 style={{ fontSize: '1rem' }}>Processed Documents</h3>
                        <button className="btn btn-secondary" onClick={loadProcessedDocs} style={{ padding: '0.4rem 0.6rem', fontSize: '0.75rem' }}>
                            <RefreshCw size={14} />
                        </button>
                    </div>

                    {loadingDocs ? (
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Loading...</p>
                    ) : processedDocs.length === 0 ? (
                        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', textAlign: 'center', padding: '2rem 0' }}>No processed documents in this processor.</p>
                    ) : (
                        <div style={{ maxHeight: '400px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                            {processedDocs.map(docId => (
                                <div key={docId}
                                    onClick={() => viewResult(docId)}
                                    style={{
                                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                        padding: '0.6rem 0.75rem', borderRadius: '6px', cursor: 'pointer',
                                        background: resultDocId === docId ? 'rgba(59, 130, 246, 0.1)' : 'rgba(255,255,255,0.02)',
                                        border: resultDocId === docId ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid var(--glass-border)',
                                        transition: 'all 0.15s', fontSize: '0.85rem'
                                    }}
                                >
                                    <span style={{ fontWeight: 500, color: resultDocId === docId ? 'var(--primary)' : 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{docId}</span>
                                    <Eye size={14} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Results Table */}
            {resultData && (
                <div className="glass-panel animate-fade-in" style={{ marginTop: '2rem', padding: '2rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                        <h3 style={{ fontSize: '1rem' }}>
                            Results — <span style={{ color: 'var(--primary)' }}>{resultDocId}</span>
                            <span style={{ color: 'var(--text-secondary)', fontWeight: 400, fontSize: '0.85rem', marginLeft: '0.75rem' }}>
                                {resultData.length} records
                            </span>
                        </h3>
                        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                            {isMerged && (
                                <select
                                    value={targetBucket}
                                    onChange={e => setTargetBucket(e.target.value)}
                                    style={{
                                        padding: '0.5rem 0.75rem',
                                        fontSize: '0.85rem',
                                        background: 'var(--bg-card)',
                                        border: '1px solid var(--glass-border)',
                                        borderRadius: '6px',
                                        color: 'var(--text-primary)',
                                        cursor: 'pointer',
                                    }}
                                >
                                    <option value="">Select target bucket…</option>
                                    {physicalBuckets.map(b => (
                                        <option key={b} value={b}>{b}</option>
                                    ))}
                                </select>
                            )}
                            <button className="btn btn-primary" onClick={saveToMongo} style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }}>
                                <Save size={16} /> Save to MongoDB
                            </button>
                        </div>
                    </div>

                    {saveStatus && (
                        <div style={{
                            padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem', fontSize: '0.85rem',
                            background: saveStatus.ok ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                            border: `1px solid ${saveStatus.ok ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                            color: saveStatus.ok ? 'var(--success)' : 'var(--danger)',
                            display: 'flex', alignItems: 'center', gap: '0.5rem'
                        }}>
                            {saveStatus.ok && <CheckCircle2 size={16} />}
                            {saveStatus.msg}
                        </div>
                    )}

                    {resultData.length > 0 ? (
                        <div style={{ overflowX: 'auto', maxHeight: '500px', overflowY: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', fontFamily: "'JetBrains Mono', monospace" }}>
                                <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
                                    <tr>
                                        <th style={{ ...thStyle, width: '40px', textAlign: 'center' }}>#</th>
                                        {Object.keys(resultData[0]).map(key => (
                                            <th key={key} style={thStyle}>{key}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {resultData.slice(0, 50).map((row, i) => (
                                        <tr key={i} style={{ borderBottom: '1px solid var(--glass-border)' }}>
                                            <td style={{ ...tdStyle, textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>{i + 1}</td>
                                            {Object.keys(resultData[0]).map(key => (
                                                <td key={key} style={tdStyle}>
                                                    {row[key] && typeof row[key] === 'object'
                                                        ? <span style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>{JSON.stringify(row[key])}</span>
                                                        : (row[key] !== undefined && row[key] !== null ? String(row[key]) : <span style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>null</span>)
                                                    }
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {resultData.length > 50 && (
                                <p style={{ textAlign: 'center', padding: '1rem', color: 'var(--text-secondary)', fontSize: '0.8rem', fontStyle: 'italic' }}>
                                    Showing first 50 of {resultData.length} records
                                </p>
                            )}
                        </div>
                    ) : (
                        <p style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>No records in this document.</p>
                    )}
                </div>
            )}
        </div>
    );
};

const thStyle: React.CSSProperties = {
    padding: '0.6rem 0.75rem',
    background: 'var(--bg-card)',
    color: 'var(--primary)',
    fontWeight: 600,
    fontSize: '0.7rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    textAlign: 'left',
    borderBottom: '2px solid var(--primary)',
    whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
    padding: '0.5rem 0.75rem',
    maxWidth: '250px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
};

export default Ingestion;
