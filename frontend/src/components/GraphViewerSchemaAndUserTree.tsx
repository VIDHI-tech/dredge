import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api/client';
import type { ExplorerMeta } from '../pages/GraphViewer';
import type { ExplorerUser, UserNodeData, ValueNode, RelatedUser } from './identityExplorer/identityExplorerTypes';
import { makeExpandKey } from './identityExplorer/identityExplorerTypes';
import { useIdentityTreeLines } from './identityExplorer/useIdentityTreeLines';
import { IdentityExplorerHeaderBar } from './identityExplorer/IdentityExplorerHeaderBar';
import { IdentityExplorerOverviewSection } from './identityExplorer/IdentityExplorerOverviewSection';
import { IdentityExplorerUserDetailSection } from './identityExplorer/IdentityExplorerUserDetailSection';
import { IdentityExplorerEmptyState } from './identityExplorer/IdentityExplorerEmptyState';

export interface GraphViewerUserTreeSectionProps {
  explorerMeta: ExplorerMeta | null;
  loading: boolean;
  refreshing: boolean;
  viewMode: string;
  onBuildUserTree: (forceRefresh?: boolean) => void;
}

export function GraphViewerUserTreeSection({
  explorerMeta,
  loading,
  refreshing,
  viewMode,
  onBuildUserTree,
}: GraphViewerUserTreeSectionProps) {
  const [users, setUsers] = useState<ExplorerUser[]>([]);
  const [pageCursors, setPageCursors] = useState<(string | null)[]>([null]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [totalUsers, setTotalUsers] = useState(0);
  const [loadingPage, setLoadingPage] = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState<ExplorerUser[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [selectedUserKey, setSelectedUserKey] = useState<string | null>(null);
  const [nodeData, setNodeData] = useState<UserNodeData | null>(null);
  const [loadingNode, setLoadingNode] = useState(false);

  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [expandedData, setExpandedData] = useState<Record<string, { users: RelatedUser[]; nextCursor: string | null; total: number }>>({});
  const [expandingKey, setExpandingKey] = useState<string | null>(null);

  const [openDetailGroupKey, setOpenDetailGroupKey] = useState<string | null>(null);

  const [navHistory, setNavHistory] = useState<string[]>([]);

  const buildId = explorerMeta?.build_id;

  const overviewInnerRef = useRef<HTMLDivElement>(null);
  const overviewRootRef = useRef<HTMLDivElement>(null);
  const userNodeRefs = useRef<(HTMLDivElement | null)[]>([]);

  const PAGE_LIMIT = 1000;

  const isSearchActive = searchQ.trim().length > 0;
  const filteredUsers = isSearchActive ? searchResults : users;

  const { svgPaths, svgW, svgH, recalc: recalcTreeLines } = useIdentityTreeLines(
    overviewInnerRef,
    overviewRootRef,
    userNodeRefs,
    [filteredUsers.length, selectedUserKey, loadingPage],
  );

  const fetchPage = useCallback(async (cursor: string | null) => {
    if (!buildId) return;
    setLoadingPage(true);
    try {
      const params: Record<string, string | number> = { build_id: buildId, limit: PAGE_LIMIT };
      if (cursor) params.cursor = cursor;
      const res = await api.get('/graph/api/user-tree/page', { params });
      const data = res.data;
      setUsers(data.items || []);
      setNextCursor(data.next_cursor || null);
      setTotalUsers(data.total_users || 0);
    } catch {
      setUsers([]);
    } finally {
      setLoadingPage(false);
    }
  }, [buildId]);

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (!searchQ.trim() || !buildId) {
      setSearchResults([]);
      return;
    }
    searchTimerRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await api.get('/graph/api/user-tree/search', {
          params: { build_id: buildId, q: searchQ.trim(), limit: 200 },
        });
        setSearchResults(res.data.items || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 350);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [searchQ, buildId]);

  useEffect(() => {
    if (buildId) {
      setPageCursors([null]);
      setSelectedUserKey(null);
      setNodeData(null);
      setExpandedKeys(new Set());
      setExpandedData({});
      setOpenDetailGroupKey(null);
      setNavHistory([]);
      fetchPage(null);
    } else {
      setUsers([]);
      setTotalUsers(0);
    }
  }, [buildId, fetchPage]);

  const fetchNode = useCallback(async (userKey: string) => {
    if (!buildId) return;
    setLoadingNode(true);
    setNodeData(null);
    setExpandedKeys(new Set());
    setExpandedData({});
    setOpenDetailGroupKey(null);
    try {
      const res = await api.get(`/graph/api/user-tree/node/${encodeURIComponent(buildId)}/${encodeURIComponent(userKey)}`);
      setNodeData(res.data);
    } catch {
      setNodeData(null);
    } finally {
      setLoadingNode(false);
    }
  }, [buildId]);

  const selectUser = (userKey: string) => {
    setNavHistory([]);
    setSelectedUserKey(userKey);
    void fetchNode(userKey);
  };

  const navigateToUser = (userKey: string) => {
    if (selectedUserKey) {
      setNavHistory(prev => [...prev, selectedUserKey]);
    }
    setSelectedUserKey(userKey);
    void fetchNode(userKey);
  };

  const goBack = () => {
    if (navHistory.length > 0) {
      const prev = navHistory[navHistory.length - 1];
      setNavHistory(h => h.slice(0, -1));
      setSelectedUserKey(prev);
      void fetchNode(prev);
    } else {
      setSelectedUserKey(null);
      setNodeData(null);
    }
  };

  const toggleExpand = async (node: ValueNode) => {
    const key = makeExpandKey(node);
    if (expandedKeys.has(key)) {
      setExpandedKeys(prev => { const n = new Set(prev); n.delete(key); return n; });
      return;
    }
    if (!buildId || !selectedUserKey) return;
    setExpandingKey(key);
    try {
      const res = await api.post('/graph/api/user-tree/expand', {
        build_id: buildId,
        user_key: selectedUserKey,
        role: node.role,
        scope: node.scope,
        norm_value: node.norm_value,
        limit: 100,
      });
      setExpandedData(prev => ({
        ...prev,
        [key]: {
          users: res.data.items || [],
          nextCursor: res.data.next_cursor || null,
          total: res.data.total || 0,
        },
      }));
      setExpandedKeys(prev => new Set(prev).add(key));
    } catch { /* ignore */ }
    finally { setExpandingKey(null); }
  };

  const loadMoreUsers = async (node: ValueNode) => {
    const key = makeExpandKey(node);
    const existing = expandedData[key];
    if (!existing?.nextCursor || !buildId || !selectedUserKey) return;
    setExpandingKey(key);
    try {
      const res = await api.post('/graph/api/user-tree/expand', {
        build_id: buildId,
        user_key: selectedUserKey,
        role: node.role,
        scope: node.scope,
        norm_value: node.norm_value,
        cursor: existing.nextCursor,
        limit: 100,
      });
      setExpandedData(prev => ({
        ...prev,
        [key]: {
          users: [...(prev[key]?.users || []), ...(res.data.items || [])],
          nextCursor: res.data.next_cursor || null,
          total: res.data.total || prev[key]?.total || 0,
        },
      }));
    } catch { /* ignore */ }
    finally { setExpandingKey(null); }
  };

  const currentPageIdx = pageCursors.length - 1;
  const goNextPage = () => {
    if (nextCursor) {
      setPageCursors(prev => [...prev, nextCursor]);
      void fetchPage(nextCursor);
    }
  };
  const goPrevPage = () => {
    if (pageCursors.length > 1) {
      const newCursors = pageCursors.slice(0, -1);
      setPageCursors(newCursors);
      void fetchPage(newCursors[newCursors.length - 1]);
    }
  };

  const overviewTreeLines = { svgPaths, svgW, svgH };

  return (
    <div className="glass-panel" style={{ padding: 0, overflow: 'hidden' }}>
      {explorerMeta && (
        <IdentityExplorerHeaderBar
          explorerMeta={explorerMeta}
          totalUsers={totalUsers}
          selectedUserKey={selectedUserKey}
          goBack={goBack}
          searchQ={searchQ}
          setSearchQ={setSearchQ}
          loading={loading}
          refreshing={refreshing}
          viewMode={viewMode}
          onBuildUserTree={onBuildUserTree}
        />
      )}

      {explorerMeta ? (
        selectedUserKey ? (
          <IdentityExplorerUserDetailSection
            loadingNode={loadingNode}
            nodeData={nodeData}
            openDetailGroupKey={openDetailGroupKey}
            setOpenDetailGroupKey={setOpenDetailGroupKey}
            expandedKeys={expandedKeys}
            expandingKey={expandingKey}
            expandedData={expandedData}
            toggleExpand={toggleExpand}
            navigateToUser={navigateToUser}
            loadMoreUsers={loadMoreUsers}
            onScrollRecalc={recalcTreeLines}
          />
        ) : (
          <IdentityExplorerOverviewSection
            totalUsers={totalUsers}
            loadingPage={loadingPage}
            filteredUsers={filteredUsers}
            isSearchActive={isSearchActive}
            searchQ={searchQ}
            searchLoading={searchLoading}
            searchResults={searchResults}
            currentPageIdx={currentPageIdx}
            PAGE_LIMIT={PAGE_LIMIT}
            nextCursor={nextCursor}
            goNextPage={goNextPage}
            goPrevPage={goPrevPage}
            selectUser={selectUser}
            overviewInnerRef={overviewInnerRef}
            overviewRootRef={overviewRootRef}
            userNodeRefs={userNodeRefs}
            overviewTreeLines={overviewTreeLines}
            onScrollRecalc={recalcTreeLines}
          />
        )
      ) : (
        <IdentityExplorerEmptyState />
      )}
    </div>
  );
}
