import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../api/client';
import { Network, Zap, Users } from 'lucide-react';
import type { ViewMode, DetailState } from '../components/GraphViewerTypes';
import { GraphViewerUserTreeSection } from '../components/GraphViewerSchemaAndUserTree';
import { GraphExplorerLandingPanel } from '../components/GraphExplorerLandingPanel';
import { GraphViewerSunburstSection } from '../components/GraphViewerSunburstSection';
import { GraphViewerDetail } from '../components/GraphViewerDetail';

export interface ExplorerMeta {
  build_id?: string;
  total_users?: number;
  total_mentions?: number;
  page_size?: number;
  sort?: string;
  status?: string;
  created_at?: number;
}

const GraphViewer = () => {
  const { currentBucket, user } = useAuth();
  const [viewMode, setViewMode] = useState<ViewMode>('schema');
  // const [schema, setSchema] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [sunburstData, setSunburstData] = useState<{ tree?: unknown; field_groups?: unknown[] } | null>(null);
  const [useLlm, setUseLlm] = useState(true);
  const [explorerMeta, setExplorerMeta] = useState<ExplorerMeta | null>(null);
  const [detail, setDetail] = useState<DetailState>({
    open: false, title: '', loading: false, type: 'table',
    rows: [], columns: [], equivalentFields: [], total: 0,
    conceptFields: [], rowData: null, history: [],
    insight: null, insightLoading: false,
  });
  const latestLoadRef = useRef<{ sunburst: string; usertree: string }>({ sunburst: '', usertree: '' });

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimeoutMs = 24 * 60 * 60 * 1000;

  const clearPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null; }
  }, []);

  useEffect(() => clearPolling, [clearPolling]);
  useEffect(() => {
    setSunburstData(null);
    setExplorerMeta(null);
    setStatusMsg('');
    latestLoadRef.current = { sunburst: '', usertree: '' };
    clearPolling();
  }, [user?.db_name, clearPolling]);
  useEffect(() => {
    if (statusMsg.includes('60 minutes')) {
      setStatusMsg('Job timed out after 24 hours - please check server logs');
    }
  }, [statusMsg]);

  const phaseMessages: Record<string, string> = {
    queued: 'Job queued…',
    schema: 'Scanning database schema…',
    llm_analysis: 'AI analyzing field relationships…',
    building_tree: 'Building tree…',
    building_index: 'Building identity index…',
    uploading: 'Uploading results…',
  };

  const loadLatestGraph = useCallback(async (type: 'sunburst' | 'usertree') => {
    if (!user?.db_name) return;
    setLoading(true);
    setStatusMsg(type === 'sunburst' ? 'Loading saved sunburst...' : 'Loading saved explorer...');
    try {
      const res = await api.get(`/graph/api/graph/latest/${type}`, { params: { use_llm: useLlm } });
      let finalResult = res.data?.result;

      // Large results (sunburst) are not inlined — stream via result_url
      if (!finalResult && res.data?.result_url) {
        setStatusMsg('Downloading graph data…');
        try {
          const dataRes = await api.get(`/graph${res.data.result_url}`);
          finalResult = dataRes.data;
        } catch {
          setStatusMsg('Failed to download graph data');
          return;
        }
      }

      if (!finalResult) {
        setStatusMsg('');
        return;
      }

      if (type === 'sunburst') {
        setSunburstData(finalResult);
        setStatusMsg('Loaded saved sunburst');
      } else {
        setExplorerMeta(finalResult);
        setStatusMsg('Loaded saved explorer');
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        setStatusMsg('');
        return;
      }
      setStatusMsg(type === 'sunburst' ? 'Failed to load saved sunburst' : 'Failed to load saved explorer');
    } finally {
      setLoading(false);
    }
  }, [user?.db_name, useLlm]);

  useEffect(() => {
    if (!user?.db_name || loading) return;

    if (viewMode === 'sunburst' && !sunburstData) {
      const key = `${user.db_name}:${useLlm}`;
      if (latestLoadRef.current.sunburst !== key) {
        latestLoadRef.current.sunburst = key;
        void loadLatestGraph('sunburst');
      }
    }

    if (viewMode === 'usertree' && !explorerMeta) {
      const key = `${user.db_name}:${useLlm}`;
      if (latestLoadRef.current.usertree !== key) {
        latestLoadRef.current.usertree = key;
        void loadLatestGraph('usertree');
      }
    }
  }, [viewMode, sunburstData, explorerMeta, user?.db_name, useLlm, loading, loadLatestGraph]);

  const pollJobStatus = useCallback((jobId: string, type: 'sunburst' | 'usertree' | 'schema') => {
    clearPolling();
    const interval = type === 'usertree' ? 5000 : 2000;
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.get(`/graph/api/graph/status/${jobId}`);
        const { status, result, result_url, error } = res.data;

        setStatusMsg(phaseMessages[status] || `Processing (${status})…`);

        if (status === 'completed') {
          clearPolling();

          let finalResult = result;
          if (result_url && !result) {
            setStatusMsg('Downloading graph data…');
            try {
              const dataRes = await api.get(`/graph${result_url}`);
              finalResult = dataRes.data;
            } catch {
              setStatusMsg('Failed to download graph data');
              setLoading(false); setRefreshing(false);
              return;
            }
          }

          if (type === 'sunburst') { setSunburstData(finalResult); setStatusMsg('Sunburst built successfully'); }
          else if (type === 'usertree') { setExplorerMeta(finalResult); setStatusMsg('Identity index built successfully'); }
          // else if (type === 'schema') { setSchema(finalResult); setStatusMsg('Schema loaded successfully'); }
          setLoading(false); setRefreshing(false);
        } else if (status === 'error') {
          clearPolling();
          setStatusMsg(error || 'Job failed');
          setLoading(false); setRefreshing(false);
        }
      } catch {
        clearPolling();
        setStatusMsg('Failed to check job status');
        setLoading(false); setRefreshing(false);
      }
    }, interval);

    timeoutRef.current = setTimeout(() => {
      if (pollRef.current) {
        clearPolling();
        setStatusMsg('Job timed out after 60 minutes — please check server logs');
        setLoading(false); setRefreshing(false);
      }
    }, pollTimeoutMs);
  }, [clearPolling, pollTimeoutMs]);

  // On mount: re-attach to any queued/in-progress jobs from a prior session
  useEffect(() => {
    if (!user?.db_name) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get('/graph/api/graph/active');
        if (cancelled) return;
        const jobs: { job_id: string; job_type: string; status: string }[] = res.data?.jobs || [];
        for (const job of jobs) {
          if (job.job_type === 'sunburst') {
            setLoading(true);
            setStatusMsg(phaseMessages[job.status] || `Resuming sunburst build (${job.status})…`);
            pollJobStatus(job.job_id, 'sunburst');
            break;
          }
          if (job.job_type === 'usertree') {
            setLoading(true);
            setStatusMsg(phaseMessages[job.status] || `Resuming identity build (${job.status})…`);
            pollJobStatus(job.job_id, 'usertree');
            break;
          }
        }
      } catch { /* no active jobs or endpoint unavailable */ }
    })();
    return () => { cancelled = true; };
  }, [user?.db_name]); // eslint-disable-line react-hooks/exhaustive-deps

  const buildSunburst = async (forceRefresh = false) => {
    if (forceRefresh) setRefreshing(true);
    const currentSunburst = sunburstData;
    setLoading(true); setStatusMsg(forceRefresh ? 'Refreshing sunburst cache…' : 'Building sunburst… (this may take a moment)'); setSunburstData(null);
    setSunburstData(currentSunburst);
    setStatusMsg(
      forceRefresh
        ? 'Refreshing sunburst cache. The current sunburst will stay available until the new build finishes.'
        : 'Building sunburst. The current sunburst will stay available until the new build finishes.'
    );
    try {
      const res = await api.post('/graph/api/graph', { target_db: user?.db_name || 'test', use_llm: useLlm, force_refresh: forceRefresh, collection: currentBucket || undefined });
      pollJobStatus(res.data.job_id, 'sunburst');
    } catch (err: unknown) {
      setStatusMsg((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to start sunburst build');
      setLoading(false); setRefreshing(false);
    }
  };

  const buildUserTree = async (forceRefresh = false) => {
    if (forceRefresh) setRefreshing(true);
    // Keep the last successful explorer visible during rebuilds
    setLoading(true);
    setStatusMsg(
      forceRefresh
        ? 'Refreshing identity index. The current explorer will stay available until the new build finishes.'
        : 'Building identity index… (this may take a moment)'
    );
    try {
      const res = await api.post('/graph/api/user-tree', { target_db: user?.db_name || 'test', use_llm: useLlm, force_refresh: forceRefresh });
      pollJobStatus(res.data.job_id, 'usertree');
    } catch (err: unknown) {
      setStatusMsg((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to start identity index build');
      setLoading(false); setRefreshing(false);
    }
  };

  const closeDetail = () => setDetail(prev => ({ ...prev, open: false, history: [] }));

  const fetchNodeInsight = async (fieldName: string, fieldValue: string) => {
    setDetail(prev => ({ ...prev, insightLoading: true, insight: null }));
    try {
      const res = await api.post('/graph/api/node-insight', { field: fieldName, value: fieldValue });
      setDetail(prev => ({ ...prev, insightLoading: false, insight: res.data }));
    } catch {
      setDetail(prev => ({ ...prev, insightLoading: false }));
    }
  };

  const fetchAndShowTable = async (fieldName: string, fieldValue: string | null, title: string, historyEntry?: () => void) => {
    const newHistory = historyEntry ? [...detail.history, historyEntry] : detail.history;
    setDetail(prev => ({ ...prev, open: true, title, loading: true, type: 'table', rows: [], columns: [], equivalentFields: [], total: 0, history: newHistory, insight: null, insightLoading: false, activeField: fieldName }));

    // If a specific value was clicked, also fetch LLM insight in parallel
    if (fieldValue) {
      fetchNodeInsight(fieldName, fieldValue);
    }

    try {
      const res = await api.post('/graph/api/query-field', { db: user?.db_name || 'test', field: fieldName, value: fieldValue || undefined });
      const data = res.data;
      const columns = (data.columns || []).filter((c: string) => c !== '_id');
      const colIdx = columns.indexOf('_collection');
      if (colIdx > 0) { columns.splice(colIdx, 1); columns.unshift('_collection'); }
      setDetail(prev => ({ ...prev, loading: false, rows: data.rows || [], columns, equivalentFields: data.equivalent_fields || [], total: data.total || 0, activeField: fieldName }));
    } catch (err: unknown) {
      setDetail(prev => ({ ...prev, loading: false, rows: [], columns: [], total: 0, title: `Error: ${(err as Error).message || 'Failed to load data'}` }));
    }
  };

  const showConceptSummary = (conceptNode: { data: { name: string }; children?: { data: { name: string }; children?: unknown; value?: number }[] }) => {
    const fields = (conceptNode.children || []).map((fieldNode: { data: { name: string }; children?: unknown; value?: number }) => ({
      name: fieldNode.data.name, valCount: fieldNode.children ? (fieldNode.children as unknown[]).length : 0, totalFreq: fieldNode.value || 0,
    }));
    setDetail({ open: true, title: conceptNode.data.name, loading: false, type: 'concept', rows: [], columns: [], equivalentFields: [], total: 0, conceptFields: fields, rowData: null, history: [], insight: null, insightLoading: false });
  };

  const showRowDetail = (row: Record<string, unknown>, prevRestore: () => void) => {
    setDetail(prev => ({ ...prev, type: 'row', title: String(row['name'] ?? row['first_name'] ?? row['title'] ?? row['_collection'] ?? 'Document Detail'), rowData: row, history: [...prev.history, prevRestore] }));
  };

  const goBack = () => {
    const prev = detail.history[detail.history.length - 1];
    if (prev) { setDetail(old => ({ ...old, history: old.history.slice(0, -1) })); prev(); }
  };

  if (!currentBucket) return (
    <div className="animate-fade-in">
      <h1 className="page-title">Graph Viewer</h1>
      <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center', marginTop: '2rem' }}>
        <Network size={48} style={{ color: 'var(--text-secondary)', marginBottom: '1rem', opacity: 0.3 }} />
        <h2 style={{ marginBottom: '0.5rem' }}>No Active Bucket</h2>
        <p style={{ color: 'var(--text-secondary)' }}>Select a bucket to explore its schema and data.</p>
      </div>
    </div>
  );

  return (
    <div className="animate-fade-in">
      <h1 className="page-title">Graph Viewer</h1>
      <p className="page-subtitle" style={{ marginBottom: '1rem' }}>
        Explore schemas and entity relationships in <b style={{ color: 'var(--primary)' }}>{currentBucket}</b>
      </p>

      {statusMsg && (
        <div style={{ fontSize: '0.8rem', padding: '0.5rem 0.75rem', marginBottom: '1rem', color: loading ? 'var(--primary)' : statusMsg.includes('Error') || statusMsg.includes('fail') ? 'var(--danger)' : '#10b981', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', border: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {loading && <div style={{ width: 14, height: 14, border: '2px solid var(--glass-border)', borderTopColor: 'var(--primary)', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />}
          {statusMsg}
        </div>
      )}

      {/* Tabs + Use LLM checkbox */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        {([
          { key: 'sunburst' as ViewMode, label: 'Sunburst Explorer', icon: <Zap size={16} /> },
          { key: 'usertree' as ViewMode, label: 'Identity Explorer', icon: <Users size={16} /> },
        ]).map(tab => (
          <button key={tab.key} className={`btn ${viewMode === tab.key ? 'btn-primary' : 'btn-secondary'}`}
            style={{ flex: 1, fontSize: '0.85rem' }} onClick={() => setViewMode(tab.key)}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>
      {(viewMode === 'sunburst' || viewMode === 'usertree') && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', fontSize: '0.85rem' }}>
          <input type="checkbox" id="use-llm" checked={useLlm} onChange={e => setUseLlm(e.target.checked)} style={{ accentColor: '#7c3aed', cursor: 'pointer' }} />
          <label htmlFor="use-llm" style={{ color: 'var(--text-secondary)', cursor: 'pointer' }}>Use AI to group related fields</label>
        </div>
      )}

      {viewMode === 'schema' && (
        <GraphExplorerLandingPanel
          onSelectSunburst={() => setViewMode('sunburst')}
          onSelectIdentity={() => setViewMode('usertree')}
        />
      )}

      {viewMode === 'sunburst' && (
        <GraphViewerSunburstSection
          sunburstData={sunburstData}
          loading={loading}
          refreshing={refreshing}
          viewMode={viewMode}
          onBuildSunburst={buildSunburst}
          onFetchAndShowTable={fetchAndShowTable}
          onShowConceptSummary={showConceptSummary}
        />
      )}

      {viewMode === 'usertree' && (
        <GraphViewerUserTreeSection
          explorerMeta={explorerMeta}
          loading={loading}
          refreshing={refreshing}
          viewMode={viewMode}
          onBuildUserTree={buildUserTree}
        />
      )}

      <GraphViewerDetail
        detail={detail}
        setDetail={setDetail}
        onClose={closeDetail}
        fetchAndShowTable={fetchAndShowTable}
        showConceptSummary={showConceptSummary}
        showRowDetail={showRowDetail}
        goBack={goBack}
      />

      <style>{`
        @keyframes spin    { 100% { transform: rotate(360deg); } }
        @keyframes fadeIn  { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
      `}</style>
    </div>
  );
};

export default GraphViewer;
