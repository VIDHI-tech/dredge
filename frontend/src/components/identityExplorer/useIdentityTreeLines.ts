import { useState, useEffect, useCallback, type RefObject, type MutableRefObject } from 'react';

/**
 * SVG connector lines from a root card to child user bubbles (overview). Call `recalc` after scroll.
 */
export function useIdentityTreeLines(
  innerRef: RefObject<HTMLDivElement | null>,
  rootRef: RefObject<HTMLDivElement | null>,
  childRefs: MutableRefObject<(HTMLDivElement | null)[]>,
  deps: unknown[],
) {
  const [svgPaths, setSvgPaths] = useState<string[]>([]);
  const [svgW, setSvgW] = useState(0);
  const [svgH, setSvgH] = useState(0);

  const calcLines = useCallback(() => {
    const inner = innerRef.current;
    const root = rootRef.current;
    if (!inner || !root || childRefs.current.length === 0) return;
    const iRect = inner.getBoundingClientRect();
    const rRect = root.getBoundingClientRect();
    const rx = rRect.left - iRect.left + rRect.width / 2;
    const ry = rRect.bottom - iRect.top;
    const centres = childRefs.current
      .map(ref => {
        if (!ref) return null;
        const rect = ref.getBoundingClientRect();
        return { x: rect.left - iRect.left + rect.width / 2, y: rect.top - iRect.top };
      })
      .filter((c): c is { x: number; y: number } => c != null);
    if (centres.length === 0) { setSvgPaths([]); return; }
    const midY = ry + (centres[0].y - ry) * 0.48;
    const paths: string[] = [];
    paths.push(`M ${rx} ${ry} V ${midY}`);
    if (centres.length > 1) paths.push(`M ${centres[0].x} ${midY} H ${centres[centres.length - 1].x}`);
    centres.forEach(c => { paths.push(`M ${c.x} ${midY} V ${c.y}`); });
    setSvgPaths(paths);
    setSvgW(inner.scrollWidth);
    setSvgH(inner.scrollHeight);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const id = requestAnimationFrame(() => { calcLines(); setTimeout(calcLines, 300); });
    const onResize = () => requestAnimationFrame(calcLines);
    window.addEventListener('resize', onResize);
    return () => { cancelAnimationFrame(id); window.removeEventListener('resize', onResize); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { svgPaths, svgW, svgH, recalc: calcLines };
}
