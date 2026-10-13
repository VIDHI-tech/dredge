import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

const DRAG_THRESHOLD_PX = 8;

export interface GrabScrollAreaProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  /** Receives scroll events (e.g. to redraw connector SVGs). */
  onScroll?: () => void;
}

/**
 * Scrollable region with grab-to-pan (drag moves scroll position) instead of relying on awkward trackpads for wide layouts.
 * Uses movement threshold so simple clicks on child elements still fire; heavy drags count as pan.
 */
export function GrabScrollArea({ children, className, style, onScroll }: GrabScrollAreaProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [grabbing, setGrabbing] = useState(false);
  const dragRef = useRef({
    active: false,
    startX: 0,
    startY: 0,
    scrollL: 0,
    scrollT: 0,
    eligible: false,
    suppressedClick: false,
  });

  const isInteractiveTarget = (el: EventTarget | null) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    return !!el.closest(
      'button, a, input, textarea, select, option, [role="button"], [contenteditable="true"], [data-no-drag-scroll]',
    );
  };

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const el = viewportRef.current;
    if (!el) return;
    if (isInteractiveTarget(e.target)) return;
    dragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      scrollL: el.scrollLeft,
      scrollT: el.scrollTop,
      eligible: true,
      suppressedClick: false,
    };
    setGrabbing(true);
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d.active || !d.eligible) return;
      const el = viewportRef.current;
      if (!el) return;
      const dx = e.clientX - d.startX;
      const dy = e.clientY - d.startY;
      if (Math.hypot(dx, dy) >= DRAG_THRESHOLD_PX) {
        d.suppressedClick = true;
        el.scrollLeft = d.scrollL - dx;
        el.scrollTop = d.scrollT - dy;
        onScroll?.();
      }
    };
    const onUp = () => {
      const d = dragRef.current;
      if (!d.active) return;
      d.active = false;
      d.eligible = false;
      setGrabbing(false);
      if (d.suppressedClick) {
        const prevent = (ev: MouseEvent) => {
          ev.preventDefault();
          ev.stopPropagation();
        };
        document.addEventListener('click', prevent, true);
        setTimeout(() => document.removeEventListener('click', prevent, true), 0);
        d.suppressedClick = false;
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [onScroll]);

  return (
    <div
      ref={viewportRef}
      className={className}
      role="presentation"
      onMouseDown={onMouseDown}
      onScroll={() => onScroll?.()}
      style={{
        overflow: 'auto',
        cursor: grabbing ? 'grabbing' : 'grab',
        userSelect: 'none',
        WebkitUserSelect: 'none',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
