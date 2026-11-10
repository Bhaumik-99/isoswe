import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useSmoothScroll } from './SmoothScrollContext';

interface FixedHeaderPortalProps {
  children: React.ReactNode;
  fallbackHeight?: number;
}

/**
 * Portals a layout's top navigation header outside #smooth-wrapper while reserving
 * exact in-flow spacer height inside #smooth-content so GSAP ScrollSmoother
 * never offsets or clips sticky chrome behind scrolled views.
 */
export const FixedHeaderPortal: React.FC<FixedHeaderPortalProps> = ({
  children,
  fallbackHeight = 64,
}) => {
  const { headerSlotEl } = useSmoothScroll();
  const measureRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number>(fallbackHeight);

  useEffect(() => {
    const el = measureRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;

    const update = () => {
      const next = Math.ceil(el.getBoundingClientRect().height);
      if (next > 0) setHeight(next);
    };
    update();

    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [headerSlotEl]);

  if (!headerSlotEl) {
    return <>{children}</>;
  }

  return (
    <>
      <div aria-hidden="true" style={{ height: `${height}px` }} className="w-full shrink-0" />
      {createPortal(
        <div ref={measureRef} className="w-full">
          {children}
        </div>,
        headerSlotEl
      )}
    </>
  );
};

