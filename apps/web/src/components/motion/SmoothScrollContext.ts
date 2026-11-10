import { createContext, useContext } from 'react';
import type ScrollSmoother from 'gsap/ScrollSmoother';

export interface SmoothScrollContextValue {
  headerSlotEl: HTMLDivElement | null;
  getSmoother: () => ScrollSmoother | undefined;
  scrollTo: (target: string | Element | number, smooth?: boolean) => void;
  scrollToTop: () => void;
  refresh: () => void;
}

export const SmoothScrollContext = createContext<SmoothScrollContextValue>({
  headerSlotEl: null,
  getSmoother: () => undefined,
  scrollTo: () => {},
  scrollToTop: () => {},
  refresh: () => {},
});

export const useSmoothScroll = () => useContext(SmoothScrollContext);

