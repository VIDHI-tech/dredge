import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';
import { Zap, RefreshCw, ZoomIn, ZoomOut, Maximize2, ChartPie, Table } from 'lucide-react';
import { SUNBURST_COLORS } from './GraphViewerTypes';
import type { SunburstNodeData } from './GraphViewerTypes';
import dredge from '../assets/dredge.png';

// ─── Prop types (identical to original) ───────────────────────────────────────

interface GraphViewerSunburstSectionProps {
  sunburstData: { tree?: unknown; field_groups?: unknown[] } | null;
  loading: boolean;
  refreshing: boolean;
  viewMode: string;
  onBuildSunburst: (forceRefresh?: boolean) => void;
  onFetchAndShowTable: (
    fieldName: string,
    fieldValue: string | null,
    title: string,
    historyEntry?: () => void,
  ) => void;
  onShowConceptSummary: (conceptNode: {
    data: { name: string };
    children?: { data: { name: string }; children?: unknown; value?: number }[];
  }) => void;
}

// ─── Internal metadata attached to every ECharts datum ────────────────────────

interface NodeMeta {
  type: 'concept' | 'field' | 'value';
  fieldOf?: string;    // concept name   (fields + values)
  fieldName?: string;  // field name     (values)
  fullValue?: string;  // raw full_value (values)
  collapsed?: boolean; // only fields
  childCount?: number; // only collapsed fields
  rawNode?: Record<string, unknown>; // reference into tree (concepts only)
}

interface SunburstTableRow {
  id: string;
  kind: 'concept' | 'field' | 'value';
  concept: string;
  field: string | null;
  value: string | null;
  count: number;
  rawConcept?: Record<string, unknown>;
}

/** Blend hex toward white so field/value rings stay in the same hue family as the concept color from `SUNBURST_COLORS`. */
function mixTowardWhite(hex: string, amount: number): string {
  const n = hex.replace('#', '').trim();
  if (n.length !== 6 || !/^[0-9a-fA-F]+$/.test(n)) return hex;
  const r = parseInt(n.slice(0, 2), 16);
  const g = parseInt(n.slice(2, 4), 16);
  const b = parseInt(n.slice(4, 6), 16);
  const t = Math.min(1, Math.max(0, amount));
  const l = (c: number) => Math.round(c + (255 - c) * t);
  return `#${[l(r), l(g), l(b)].map((x) => x.toString(16).padStart(2, '0')).join('')}`;
}

// ─── Data-conversion helpers ───────────────────────────────────────────────────

/**
 * Convert our backend tree into the nested array ECharts sunburst expects.
 * Fields that are NOT in `expanded` are rendered as collapsed single-wedge
 * nodes so only their count is visible — this keeps the rendered arc count low.
 */
function buildEChartsTree(
  tree: Record<string, unknown>,
  expanded: Set<string>,
): echarts.SunburstSeriesOption['data'] {
  const concepts = (tree.children ?? []) as Record<string, unknown>[];

  return concepts.map((concept, ci) => {
    const conceptName = String(concept.name ?? '');
    const fields = (concept.children ?? []) as Record<string, unknown>[];
    const baseColor = SUNBURST_COLORS[ci % SUNBURST_COLORS.length];
    const fieldColor = mixTowardWhite(baseColor, 0.14);
    const valueColor = mixTowardWhite(baseColor, 0.32);

    return {
      name: conceptName,
      itemStyle: { color: baseColor, opacity: 0.92 },
      _meta: { type: 'concept', rawNode: concept } as NodeMeta,
      children: fields.map((field) => {
        const fieldName = String(field.name ?? '');
        const fieldKey = `${conceptName}::${fieldName}`;
        const isExpanded = expanded.has(fieldKey);
        const values = (field.children ?? []) as Record<string, unknown>[];

        if (isExpanded) {
          // Fan out into individual value arcs
          return {
            name: fieldName,
            itemStyle: { color: fieldColor },
            _meta: { type: 'field', fieldOf: conceptName, collapsed: false } as NodeMeta,
            children: values.map((v) => {
              const vn = v as SunburstNodeData & { value?: number };
              return {
                name: String(vn.name ?? ''),
                value: vn.value ?? 1,
                itemStyle: { color: valueColor },
                _meta: {
                  type: 'value',
                  fieldOf: conceptName,
                  fieldName,
                  fullValue: String(vn.full_value ?? vn.name ?? ''),
                } as NodeMeta,
              };
            }),
          };
        }

        // Collapsed: a single wedge proportional to value count
        return {
          name: fieldName,
          value: Math.max(values.length, 1),
          itemStyle: { color: fieldColor },
          _meta: {
            type: 'field',
            fieldOf: conceptName,
            collapsed: true,
            childCount: values.length,
          } as NodeMeta,
        };
      }),
    };
  });
}

/** Reconstruct the D3-style argument that onShowConceptSummary expects. */
function toConceptSummaryArg(rawNode: Record<string, unknown>) {
  return {
    data: { name: String(rawNode.name ?? '') },
    children: ((rawNode.children ?? []) as Record<string, unknown>[]).map((f) => ({
      data: { name: String(f.name ?? '') },
      children: f.children as unknown,
      value: ((f.children ?? []) as unknown[]).length,
    })),
  };
}

function flattenTreeToTableRows(tree: Record<string, unknown>): SunburstTableRow[] {
  const concepts = (tree.children ?? []) as Record<string, unknown>[];
  const rows: SunburstTableRow[] = [];
  concepts.forEach((concept) => {
    const conceptName = String(concept.name ?? '');
    const fields = (concept.children ?? []) as Record<string, unknown>[];
    const conceptRows: SunburstTableRow[] = [];
    let conceptCount = 0;
    fields.forEach((field) => {
      const fieldName = String(field.name ?? '');
      const values = (field.children ?? []) as Record<string, unknown>[];
      const fieldCount = values.reduce((sum, v) => sum + Number((v as SunburstNodeData & { value?: number }).value ?? 1), 0);
      conceptCount += fieldCount;
      conceptRows.push({
        id: `field::${conceptName}::${fieldName}`,
        kind: 'field',
        concept: conceptName,
        field: fieldName,
        value: null,
        count: Math.max(values.length, fieldCount, 1),
      });
      values.forEach((valueNode, valueIdx) => {
        const vn = valueNode as SunburstNodeData & { value?: number };
        const valueText = String(vn.full_value ?? vn.name ?? '');
        conceptRows.push({
          id: `value::${conceptName}::${fieldName}::${valueIdx}::${valueText}`,
          kind: 'value',
          concept: conceptName,
          field: fieldName,
          value: valueText,
          count: Number(vn.value ?? 1),
        });
      });
    });
    rows.push({
      id: `concept::${conceptName}`,
      kind: 'concept',
      concept: conceptName,
      field: null,
      value: null,
      count: conceptCount,
      rawConcept: concept,
    });
    rows.push(...conceptRows);
  });
  return rows;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function GraphViewerSunburstSection({
  sunburstData,
  loading,
  refreshing,
  viewMode,
  onBuildSunburst,
  onFetchAndShowTable,
  onShowConceptSummary,
}: GraphViewerSunburstSectionProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const expandedFields = useRef<Set<string>>(new Set());
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** CSS pan/zoom on the chart canvas so dense outer rings can be inspected (wheel = zoom to cursor). */
  const [zoomPan, setZoomPan] = useState({ s: 1, tx: 0, ty: 0 });
  const [displayMode, setDisplayMode] = useState<'chart' | 'table'>('chart');
  const [selectedSidebarItem, setSelectedSidebarItem] = useState<SunburstTableRow | null>(null);
  const [selectedTableRowId, setSelectedTableRowId] = useState<string | null>(null);
  const TABLE_PAGE_SIZE = 250;
  const [tableVisibleCount, setTableVisibleCount] = useState(TABLE_PAGE_SIZE);

  const tableRows = useMemo(() => {
    if (!sunburstData?.tree) return [];
    return flattenTreeToTableRows(sunburstData.tree as Record<string, unknown>);
  }, [sunburstData]);

  const visibleTableRows = useMemo(
    () => tableRows.slice(0, tableVisibleCount),
    [tableRows, tableVisibleCount],
  );

  useEffect(() => {
    setZoomPan({ s: 1, tx: 0, ty: 0 });
    setTableVisibleCount(TABLE_PAGE_SIZE);
    setSelectedTableRowId(null);
    setSelectedSidebarItem(null);
  }, [sunburstData]);

  const applyZoomAt = useCallback((mx: number, my: number, scaleDelta: number) => {
    setZoomPan((prev) => {
      const ns = Math.min(5, Math.max(0.35, prev.s * scaleDelta));
      const factor = ns / prev.s;
      return {
        s: ns,
        tx: mx - (mx - prev.tx) * factor,
        ty: my - (my - prev.ty) * factor,
      };
    });
  }, []);

  const zoomFromCenter = useCallback((factor: number) => {
    const v = viewportRef.current;
    if (!v) return;
    const { width, height } = v.getBoundingClientRect();
    applyZoomAt(width / 2, height / 2, factor);
  }, [applyZoomAt]);

  useEffect(() => {
    const v = viewportRef.current;
    if (!v || !sunburstData?.tree) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = v.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const delta = e.deltaY > 0 ? 0.92 : 1.08;
      applyZoomAt(mx, my, delta);
    };
    v.addEventListener('wheel', onWheel, { passive: false });
    return () => v.removeEventListener('wheel', onWheel);
  }, [sunburstData?.tree, applyZoomAt]);

  // ── Build ECharts option ──────────────────────────────────────────────────

  const buildOption = useCallback(
    (eData: echarts.SunburstSeriesOption['data']): echarts.EChartsOption => {
      return {
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'item',
          confine: true,
          backgroundColor: 'rgba(255,255,255,0.97)',
          borderColor: 'rgba(13,148,136,0.25)',
          borderWidth: 1,
          padding: [10, 14],
          textStyle: { color: '#1e293b', fontSize: 12, fontFamily: 'Inter, sans-serif' },
          extraCssText:
            'backdrop-filter:blur(8px);border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,0.12);',
          formatter: (params: unknown) => {
            const p = params as {
              data: { name: string; _meta?: NodeMeta };
              treePathInfo: Array<{ name: string }>;
            };
            const { name, _meta: meta } = p.data;
            const path = p.treePathInfo.slice(1).map((t) => t.name).join(' → ');

            if (!meta) return `<strong>${name}</strong>`;
            if (meta.type === 'concept') {
              return `<strong>${name}</strong><br/><span style="opacity:.6">Click for concept summary</span>`;
            }
            if (meta.type === 'field' && meta.collapsed) {
              return (
                `<strong>${name}</strong><br/>` +
                `<span style="opacity:.6">Click to expand (${meta.childCount} values)</span><br/>` +
                `<span style="opacity:.45">Double-click to query all</span>`
              );
            }
            if (meta.type === 'field') {
              return (
                `<strong>${name}</strong><br/>` +
                `<span style="opacity:.6">${path}</span><br/>` +
                `<span style="opacity:.45">Click to collapse · Double-click to query</span>`
              );
            }
            // value leaf
            return (
              `<strong>${name}</strong><br/>` +
              `<span style="opacity:.6">${path}</span><br/>` +
              `<span style="opacity:.45">Double-click to query</span>`
            );
          },
        },
        series: [
          {
            type: 'sunburst' as const,
            data: eData,
            color: SUNBURST_COLORS,
            radius: ['8%', '100%'],
            nodeClick: false,   // we handle all interactions manually
            sort: undefined,
            emphasis: { focus: 'ancestor', itemStyle: { opacity: 1 } },
            label: {
              show: true,
              overflow: 'truncate',
              minAngle: 5,
              formatter: (params: unknown) => {
                const p = params as { data: { name: string; _meta?: NodeMeta } };
                const { name, _meta: meta } = p.data;
                if (meta?.type === 'field' && meta.collapsed) {
                  return `${name} (${meta.childCount})`;
                }
                return name;
              },
            },
            itemStyle: {
              borderWidth: 1,
              borderColor: 'rgba(255,255,255,0.75)',
            },
            levels: [
              {}, // virtual root — not rendered
              {
                // Concept ring
                r0: '8%', r: '32%',
                label: { fontSize: 11, fontWeight: 'bold' as const },
                itemStyle: { borderWidth: 2, borderColor: 'rgba(255,255,255,0.9)' },
              },
              {
                // Field ring
                r0: '32%', r: '60%',
                label: { fontSize: 10 },
                itemStyle: { borderWidth: 1.5, opacity: 0.88 },
              },
              {
                // Value ring (only visible when a field is expanded)
                r0: '60%', r: '88%',
                label: { fontSize: 8 },
                itemStyle: { borderWidth: 1, opacity: 0.80 },
              },
            ],
          },
        ],
        // Centre label overlay — intentionally blank (user ID removed)
        graphic: [],
      };
    },
    [sunburstData],
  );

  // ── Render / update ───────────────────────────────────────────────────────

  const renderChart = useCallback(() => {
    const container = containerRef.current;
    if (!container || !sunburstData?.tree) return;

    // Recreate instance when the chart DOM remounts (e.g., table -> chart toggle).
    if (chartRef.current && !chartRef.current.isDisposed() && chartRef.current.getDom() !== container) {
      chartRef.current.dispose();
      chartRef.current = null;
    }

    // Lazily initialise the chart instance
    if (!chartRef.current || chartRef.current.isDisposed()) {
      chartRef.current = echarts.init(container, null, {
        renderer: 'canvas',  // Canvas rendering — 3–9× faster than SVG for large data
        useDirtyRect: true,  // Incremental repaints only
      });
    }

    const chart = chartRef.current;

    const eData = buildEChartsTree(
      sunburstData.tree as Record<string, unknown>,
      expandedFields.current,
    );

    chart.setOption(buildOption(eData), { notMerge: true, lazyUpdate: false });

    // ── Click handler (single / double detection via 240 ms timer) ──────────
    chart.off('click');
    chart.on('click', (params: unknown) => {
      const p = params as {
        data: { name: string; _meta?: NodeMeta };
        treePathInfo: Array<{ name: string }>;
      };
      if (!p?.data) return;

      const { name, _meta: meta } = p.data;
      // ECharts sunburst always inserts a virtual root, so treePathInfo is
      // [virtualRoot, concept] (len 2), [..., field] (3), [..., value] (4).
      // Do not use treePathInfo.length as "depth" — it never matched 1/2/3 and no handler ran.
      if (!meta?.type) return;
      const kind = meta.type;

      const handleSingle = () => {
        if (kind === 'concept' && meta.rawNode) {
          setSelectedSidebarItem({
            id: `concept::${name}`,
            kind: 'concept',
            concept: name,
            field: null,
            value: null,
            count: 0,
            rawConcept: meta.rawNode,
          });
          onShowConceptSummary(
            toConceptSummaryArg(meta.rawNode) as Parameters<typeof onShowConceptSummary>[0],
          );
          return;
        }
        if (kind === 'field') {
          setSelectedSidebarItem({
            id: `field::${meta.fieldOf ?? ''}::${name}`,
            kind: 'field',
            concept: meta.fieldOf ?? '',
            field: name,
            value: null,
            count: meta.childCount ?? 0,
          });
          const key = `${meta.fieldOf ?? ''}::${name}`;
          if (meta.collapsed) {
            expandedFields.current.add(key);
          } else {
            expandedFields.current.delete(key);
          }
          renderChart();
        }
      };

      const handleDouble = () => {
        if (kind === 'value') {
          const fName = meta.fieldName ?? '';
          const fValue = meta.fullValue ?? name;
          setSelectedSidebarItem({
            id: `value::${meta.fieldOf ?? ''}::${fName}::${fValue}`,
            kind: 'value',
            concept: meta.fieldOf ?? '',
            field: fName,
            value: fValue,
            count: 1,
          });
          onFetchAndShowTable(fName, fValue, `${fName} = "${fValue}"`);
          return;
        }
        if (kind === 'field') {
          setSelectedSidebarItem({
            id: `field::${meta.fieldOf ?? ''}::${name}`,
            kind: 'field',
            concept: meta.fieldOf ?? '',
            field: name,
            value: null,
            count: meta.childCount ?? 0,
          });
          onFetchAndShowTable(name, null, `All "${name}" records`);
        }
      };

      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
        handleDouble();
      } else {
        clickTimerRef.current = setTimeout(() => {
          clickTimerRef.current = null;
          handleSingle();
        }, 240);
      }
    });
  }, [sunburstData, buildOption, onFetchAndShowTable, onShowConceptSummary]);

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    if (sunburstData) renderChart();
  }, [sunburstData, renderChart]);

  useEffect(() => {
    if (displayMode !== 'chart' || !sunburstData) return;
    const raf = requestAnimationFrame(() => {
      renderChart();
      chartRef.current?.resize();
    });
    return () => cancelAnimationFrame(raf);
  }, [displayMode, sunburstData, renderChart]);

  // Resize observer — observe viewport so layout matches visible plot area
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => chartRef.current?.resize());
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Cleanup on unmount
  useEffect(
    () => () => {
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      chartRef.current?.dispose();
      chartRef.current = null;
    },
    [],
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="glass-panel" style={{ padding: 0, overflow: 'hidden' }}>
      <style>{`
        @keyframes graphShimmerSweep {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
        @keyframes graphSunburstSpin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes graphSunburstPulse {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 0.85; }
        }
      `}</style>

      {/* ── Header bar ─────────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '1.25rem 1.5rem',
          borderBottom: '1px solid var(--glass-border)',
          background: 'rgba(255,255,255,0.5)',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <h3
          style={{
            fontSize: '1rem',
            margin: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            color: 'var(--primary)',
            fontWeight: 700,
            letterSpacing: '0.02em',
          }}
        >
          <Zap size={18} /> Sunburst Explorer
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'inline-flex', border: '1px solid var(--glass-border)', borderRadius: 10, overflow: 'hidden' }}>
            <button
              type="button"
              className={displayMode === 'chart' ? 'btn btn-primary' : 'btn btn-secondary'}
              onClick={() => setDisplayMode('chart')}
              style={{ borderRadius: 0, padding: '0.5rem 1rem', fontSize: '0.85rem', display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none' }}
              title="Chart view"
              aria-label="Chart view"
            >
              <ChartPie size={16} />
            </button>
            <button
              type="button"
              className={displayMode === 'table' ? 'btn btn-primary' : 'btn btn-secondary'}
              onClick={() => setDisplayMode('table')}
              style={{ borderRadius: 0, padding: '0.5rem 1rem', fontSize: '0.85rem', display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none' }}
              title="Table view"
              aria-label="Table view"
            >
              <Table size={16} />
            </button>
          </div>

          <button
            className="btn btn-primary"
            onClick={() => onBuildSunburst()}
            disabled={loading}
            style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }}
          >
            {loading && viewMode === 'sunburst' && !refreshing ? 'Building…' : 'Build Sunburst'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => onBuildSunburst(true)}
            disabled={loading}
            style={{
              padding: '0.5rem 0.75rem',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            <RefreshCw
              size={14}
              style={
                refreshing && viewMode === 'sunburst'
                  ? { animation: 'spin 0.8s linear infinite' }
                  : undefined
              }
            />
            Refresh Cache
          </button>
        </div>
      </div>

      {/* ── Content row ────────────────────────────────────────────────────── */}
      <div
        className="sunburst-layout"
        style={{ display: 'flex', flexDirection: 'row', minHeight: '600px', maxHeight: '700px' }}
      >

        {/* Sidebar — shown when data is loaded or loading */}
        {(sunburstData || (loading && viewMode === 'sunburst')) && (
          <aside
            style={{
              width: '200px',
              flexShrink: 0,
              padding: '1rem 1.25rem',
              borderRight: '1px solid var(--glass-border)',
              background: 'var(--bg-card)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
              overflowY: 'scroll'
            }}
          >
            {!sunburstData && loading ? (
              <>
                <div style={{ height: 74, borderRadius: 10, background: 'linear-gradient(90deg, rgba(15,23,42,0.06) 25%, rgba(15,23,42,0.12) 50%, rgba(15,23,42,0.06) 75%)', backgroundSize: '200% 100%', animation: 'graphShimmerSweep 1.4s linear infinite' }} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} style={{ height: 30, borderRadius: 8, background: 'linear-gradient(90deg, rgba(15,23,42,0.06) 25%, rgba(15,23,42,0.12) 50%, rgba(15,23,42,0.06) 75%)', backgroundSize: '200% 100%', animation: `graphShimmerSweep 1.4s linear infinite ${i * 0.08}s` }} />
                  ))}
                </div>
              </>
            ) : (
              <>
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    background: 'var(--primary-light)',
                    borderRadius: '10px',
                    border: '1px solid rgba(13,148,136,0.2)',
                    fontSize: '0.8rem',
                    lineHeight: 1.45,
                  }}
                >
                  <span style={{ fontWeight: 600, color: 'var(--primary)' }}>💡 Tip</span>
                  <p style={{ margin: '0.5rem 0 0', color: 'var(--text-secondary)' }}>
                    {displayMode === 'chart'
                      ? 'Click a field arc to expand its values. Double-click a value to query records.'
                      : 'Click any table row to open the same field/value query used in chart mode.'}
                  </p>
                </div>
                {selectedSidebarItem && (
                  <div
                    style={{
                      padding: '0.7rem 0.85rem',
                      borderRadius: 10,
                      border: '1px solid rgba(13,148,136,0.22)',
                      background: 'rgba(13,148,136,0.07)',
                    }}
                  >
                    <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: 4 }}>
                      Selected
                    </div>
                    <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {selectedSidebarItem.kind === 'concept'
                        ? selectedSidebarItem.concept
                        : selectedSidebarItem.kind === 'field'
                          ? selectedSidebarItem.field
                          : selectedSidebarItem.value}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                      {selectedSidebarItem.kind.toUpperCase()} · {selectedSidebarItem.concept}
                    </div>
                  </div>
                )}

                {(sunburstData?.field_groups ?? []).length > 0 && (
                  <div>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        color: 'var(--primary)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                      }}
                    >
                      AI Field Groups
                    </span>
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.5rem',
                        marginTop: '0.6rem' 
                      }}
                    >
                      {sunburstData!.field_groups!.map((g: unknown, i: number) => (
                        <span
                          key={i}
                          style={{
                            background: 'var(--primary-light)',
                            padding: '6px 10px',
                            borderRadius: '8px',
                            fontSize: '0.78rem',
                            color: 'var(--primary)',
                            border: '1px solid rgba(13,148,136,0.2)',
                            fontWeight: 500,
                          }}
                        >
                          {typeof g === 'string'
                            ? g
                            : (g as { concept?: string }).concept ?? JSON.stringify(g)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </aside>
        )}

        {/* Graph / table area */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            position: 'relative',
          }}
        >
          {/* Watermark background (empty state) */}
          {!sunburstData && (
            <div
              aria-hidden="true"
              style={{
                position: 'absolute',
                inset: 0,
                zIndex: 0,
                backgroundImage: `linear-gradient(to bottom,rgba(248,250,252,0.92) 0%,rgba(241,245,249,0.88) 50%,rgba(248,250,252,0.92) 100%),url(${dredge})`,
                backgroundPosition: 'center',
                backgroundRepeat: 'no-repeat',
                pointerEvents: 'none',
                borderRadius: '0 0 16px 16px',
              }}
            />
          )}

          {displayMode === 'chart' ? (
            <div
              ref={viewportRef}
              style={{
                position: 'relative',
                zIndex: 1,
                display: 'flex',
                flexDirection: 'column',
                background: sunburstData
                  ? 'radial-gradient(ellipse at center, var(--bg-darker) 0%, var(--bg-page) 60%)'
                  : 'transparent',
                borderRadius: sunburstData ? '0 0 16px 0' : '0 0 16px 16px',
                border: '1px solid var(--glass-border)',
                ...(sunburstData ? { borderLeft: 'none' } : {}),
                minHeight: '550px',
                flex: 1,
                minWidth: 0,
                overflow: 'hidden',
                touchAction: sunburstData ? 'none' : undefined,
              }}
            >
              {sunburstData && (
                <div
                  style={{
                    position: 'absolute',
                    top: 10,
                    right: 10,
                    zIndex: 6,
                    display: 'flex',
                    gap: 6,
                    alignItems: 'center',
                    pointerEvents: 'auto',
                  }}
                >
                  <span
                    style={{
                      fontSize: '0.72rem',
                      color: 'var(--text-secondary)',
                      marginRight: 4,
                      userSelect: 'none',
                      textShadow: '0 0 8px var(--bg-page)',
                    }}
                  >
                    {Math.round(zoomPan.s * 100)}%
                  </span>
                  <button type="button" className="btn btn-secondary" title="Zoom in" aria-label="Zoom in" onClick={() => zoomFromCenter(1.15)} style={{ padding: '0.35rem 0.5rem', display: 'flex', alignItems: 'center' }}>
                    <ZoomIn size={16} />
                  </button>
                  <button type="button" className="btn btn-secondary" title="Zoom out" aria-label="Zoom out" onClick={() => zoomFromCenter(1 / 1.15)} style={{ padding: '0.35rem 0.5rem', display: 'flex', alignItems: 'center' }}>
                    <ZoomOut size={16} />
                  </button>
                  <button type="button" className="btn btn-secondary" title="Reset zoom" aria-label="Reset zoom" onClick={() => setZoomPan({ s: 1, tx: 0, ty: 0 })} style={{ padding: '0.35rem 0.5rem', display: 'flex', alignItems: 'center' }}>
                    <Maximize2 size={16} />
                  </button>
                </div>
              )}
              <div
                style={{
                  width: '100%',
                  height: '100%',
                  minHeight: 550,
                  flex: 1,
                  transform: `translate(${zoomPan.tx}px, ${zoomPan.ty}px) scale(${zoomPan.s})`,
                  transformOrigin: '0 0',
                }}
              >
                <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 550 }} />
              </div>
              {loading && viewMode === 'sunburst' && (
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    zIndex: 2,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexDirection: 'column',
                    gap: '0.9rem',
                    background: 'rgba(248,250,252,0.62)',
                    backdropFilter: 'blur(1.5px)',
                  }}
                >
                  <div
                    style={{
                      position: 'relative',
                      width: 340,
                      height: 340,
                      borderRadius: '50%',
                      animation: 'graphSunburstPulse 1.8s ease-in-out infinite',
                    }}
                  >
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        borderRadius: '50%',
                        background: 'conic-gradient(from 0deg, rgba(13,148,136,0.08), rgba(56,189,248,0.22), rgba(99,102,241,0.16), rgba(236,72,153,0.14), rgba(13,148,136,0.08))',
                        animation: 'graphSunburstSpin 2.6s linear infinite',
                      }}
                    />
                    <div
                      style={{
                        position: 'absolute',
                        inset: 34,
                        borderRadius: '50%',
                        border: '1px solid rgba(13,148,136,0.2)',
                        background: 'conic-gradient(from 180deg, rgba(13,148,136,0.05), rgba(56,189,248,0.14), rgba(13,148,136,0.05))',
                        animation: 'graphSunburstSpin 3.2s linear infinite reverse',
                      }}
                    />
                    <div
                      style={{
                        position: 'absolute',
                        inset: 90,
                        borderRadius: '50%',
                        border: '1px solid rgba(13,148,136,0.2)',
                        background: 'radial-gradient(circle, rgba(255,255,255,0.95) 0%, rgba(241,245,249,0.92) 60%, rgba(226,232,240,0.85) 100%)',
                      }}
                    />
                  </div>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Loading sunburst data...</div>
                </div>
              )}
              {!sunburstData && !loading && (
                <div style={{ textAlign: 'center', padding: '1rem 2rem', color: 'var(--text-secondary)', position: 'relative', zIndex: 1 }}>
                  <Zap size={48} style={{ opacity: 0.2, margin: '0 auto 1rem', display: 'block', color: 'var(--primary)' }} />
                  <p style={{ fontSize: '0.95rem' }}>
                    Click &quot;Build Sunburst&quot; to generate the radial visualization.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div
              style={{
                position: 'relative',
                zIndex: 1,
                display: 'flex',
                flexDirection: 'column',
                border: '1px solid var(--glass-border)',
                borderRadius: '0 0 16px 0',
                minHeight: 550,
                overflow: 'hidden',
                background: 'var(--bg-card)',
              }}
            >
              {!sunburstData && loading ? (
                <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {Array.from({ length: 10 }).map((_, i) => (
                    <div key={i} style={{ height: 34, borderRadius: 8, background: 'linear-gradient(90deg, rgba(15,23,42,0.06) 25%, rgba(15,23,42,0.12) 50%, rgba(15,23,42,0.06) 75%)', backgroundSize: '200% 100%', animation: `graphShimmerSweep 1.2s linear infinite ${i * 0.04}s` }} />
                  ))}
                </div>
              ) : !sunburstData ? (
                <div style={{ textAlign: 'center', padding: '6rem 2rem', color: 'var(--text-secondary)' }}>
                  <p style={{ fontSize: '0.95rem' }}>Build sunburst data to view the table.</p>
                </div>
              ) : (
                <>
                  <div style={{ overflowX: 'auto', overflowY: 'auto', height: '65vh', maxHeight: '65vh' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760, tableLayout: 'fixed' }}>
                      <thead>
                        <tr style={{ background: 'rgba(13,148,136,0.08)' }}>
                          <th style={{ position: 'sticky', top: 0, zIndex: 2, background: 'rgba(222,247,243,0.95)', backdropFilter: 'blur(6px)', textAlign: 'left', padding: '0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.78rem' }}>Type</th>
                          <th style={{ position: 'sticky', top: 0, zIndex: 2, background: 'rgba(222,247,243,0.95)', backdropFilter: 'blur(6px)', textAlign: 'left', padding: '0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.78rem' }}>Concept</th>
                          <th style={{ position: 'sticky', top: 0, zIndex: 2, background: 'rgba(222,247,243,0.95)', backdropFilter: 'blur(6px)', textAlign: 'left', padding: '0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.78rem' }}>Field</th>
                          <th style={{ position: 'sticky', top: 0, zIndex: 2, background: 'rgba(222,247,243,0.95)', backdropFilter: 'blur(6px)', textAlign: 'left', padding: '0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.78rem' }}>Value</th>
                          <th style={{ position: 'sticky', top: 0, zIndex: 2, background: 'rgba(222,247,243,0.95)', backdropFilter: 'blur(6px)', textAlign: 'right', padding: '0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.78rem' }}>Count</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleTableRows.map((row) => (
                          <tr
                            key={row.id}
                            onClick={() => {
                              setSelectedTableRowId(row.id);
                              setSelectedSidebarItem(row);
                              if (row.kind === 'concept' && row.rawConcept) {
                                onShowConceptSummary(toConceptSummaryArg(row.rawConcept) as Parameters<typeof onShowConceptSummary>[0]);
                                return;
                              }
                              if (row.kind === 'field' && row.field) {
                                onFetchAndShowTable(row.field, null, `All "${row.field}" records`);
                                return;
                              }
                              if (row.kind === 'value' && row.field && row.value !== null) {
                                onFetchAndShowTable(row.field, row.value, `${row.field} = "${row.value}"`);
                              }
                            }}
                            style={{
                              cursor: 'pointer',
                              background: selectedTableRowId === row.id ? 'rgba(13,148,136,0.12)' : 'transparent',
                            }}
                          >
                            <td style={{ padding: '0.65rem 0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.8rem', textTransform: 'capitalize' }}>{row.kind}</td>
                            <td style={{ padding: '0.65rem 0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem', fontWeight: 600 }}>{row.concept}</td>
                            <td style={{ padding: '0.65rem 0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem' }}>{row.field ?? '-'}</td>
                            <td style={{ padding: '0.65rem 0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.value ?? '-'}</td>
                            <td style={{ padding: '0.65rem 0.75rem', borderBottom: '1px solid var(--glass-border)', fontSize: '0.82rem', textAlign: 'right' }}>{row.count.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ padding: '0.9rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--glass-border)', background: 'rgba(255,255,255,0.5)' }}>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                      Showing {visibleTableRows.length.toLocaleString()} of {tableRows.length.toLocaleString()} rows
                    </span>
                    {visibleTableRows.length < tableRows.length && (
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setTableVisibleCount((prev) => prev + TABLE_PAGE_SIZE)}
                        style={{ padding: '0.45rem 0.75rem', fontSize: '0.78rem' }}
                      >
                        Load more
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
