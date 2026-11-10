import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ScrollSmoother } from 'gsap/ScrollSmoother';
import { useGSAP } from '@gsap/react';
import { ArrowUp } from 'lucide-react';
import { SmoothScrollContext } from './SmoothScrollContext';

gsap.registerPlugin(ScrollTrigger, ScrollSmoother, useGSAP);

interface SmoothScrollProviderProps {
  children: React.ReactNode;
}

export const SmoothScrollProvider: React.FC<SmoothScrollProviderProps> = ({ children }) => {
  const { pathname } = useLocation();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const progressBarRef = useRef<HTMLDivElement>(null);
  const smootherRef = useRef<ScrollSmoother | null>(null);

  const [headerSlotEl, setHeaderSlotEl] = useState<HTMLDivElement | null>(null);
  const [showBackToTop, setShowBackToTop] = useState(false);

  const updateProgressUI = useCallback((progress: number, scrollY: number) => {
    const clamped = Math.max(0, Math.min(1, progress));
    if (progressBarRef.current) {
      progressBarRef.current.style.transform = `scaleX(${clamped})`;
    }
    setShowBackToTop(scrollY > 320);
  }, []);

  useGSAP(
    () => {
      if (typeof window === 'undefined' || !wrapperRef.current || !contentRef.current) {
        return;
      }

      const mm = gsap.matchMedia();

      mm.add('(prefers-reduced-motion: no-preference)', () => {
        const smoother = ScrollSmoother.create({
          wrapper: wrapperRef.current!,
          content: contentRef.current!,
          smooth: 1.15,
          effects: true,
          smoothTouch: 0.1,
          ignoreMobileResize: true,
          normalizeScroll: false,
          onUpdate: (self) => {
            updateProgressUI(self.progress, self.scrollTop());
          },
        });

        smootherRef.current = smoother;

        return () => {
          smootherRef.current = null;
          smoother.kill();
        };
      });

      mm.add('(prefers-reduced-motion: reduce)', () => {
        const handleNativeScroll = () => {
          const maxScroll = Math.max(
            1,
            document.documentElement.scrollHeight - window.innerHeight
          );
          updateProgressUI(window.scrollY / maxScroll, window.scrollY);
        };
        window.addEventListener('scroll', handleNativeScroll, { passive: true });
        return () => {
          window.removeEventListener('scroll', handleNativeScroll);
        };
      });

      return () => {
        mm.revert();
      };
    },
    { scope: wrapperRef }
  );

  // Recalculate ScrollSmoother & ScrollTrigger whenever dynamic content changes height
  useEffect(() => {
    if (typeof window === 'undefined' || !contentRef.current) return;
    if (typeof ResizeObserver === 'undefined') return;

    let rafId: number | null = null;
    const observer = new ResizeObserver(() => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        ScrollTrigger.refresh(true);
      });
    });

    observer.observe(contentRef.current);

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, []);

  // Reset scroll to top cleanly when navigating between portal routes
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const smoother = smootherRef.current || ScrollSmoother.get();
    if (smoother) {
      smoother.scrollTo(0, false);
    } else {
      window.scrollTo(0, 0);
    }
    updateProgressUI(0, 0);

    const rafId = requestAnimationFrame(() => {
      ScrollTrigger.refresh(true);
    });
    return () => cancelAnimationFrame(rafId);
  }, [pathname, updateProgressUI]);

  const scrollTo = useCallback((target: string | Element | number, smooth = true) => {
    const smoother = smootherRef.current || ScrollSmoother.get();
    if (smoother) {
      smoother.scrollTo(target, smooth);
      return;
    }
    if (typeof target === 'number') {
      window.scrollTo({ top: target, behavior: smooth ? 'smooth' : 'auto' });
      return;
    }
    const el = typeof target === 'string' ? document.querySelector(target) : target;
    el?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' });
  }, []);

  const scrollToTop = useCallback(() => {
    scrollTo(0, true);
  }, [scrollTo]);

  const refresh = useCallback(() => {
    ScrollTrigger.refresh(true);
  }, []);

  const contextValue = useMemo(
    () => ({
      headerSlotEl,
      getSmoother: () => smootherRef.current || ScrollSmoother.get(),
      scrollTo,
      scrollToTop,
      refresh,
    }),
    [headerSlotEl, scrollTo, scrollToTop, refresh]
  );

  return (
    <SmoothScrollContext.Provider value={contextValue}>
      {/* Skip-to-main link for keyboard accessibility (UI/UX Pro Max Priority 1) */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:px-4 focus:py-2.5 focus:rounded-xl focus:bg-primary-600 focus:text-white focus:text-sm focus:font-semibold focus:shadow-lg"
      >
        Skip to main content
      </a>

      {/* Fixed Header Portal Container — stays outside transformed #smooth-content */}
      <div
        ref={setHeaderSlotEl}
        id="app-header-portal"
        className="fixed top-0 inset-x-0 z-30 pointer-events-none [&>*]:pointer-events-auto"
      />

      {/* Top Smooth Scroll Progress Bar */}
      <div
        aria-hidden="true"
        className="fixed top-0 left-0 right-0 h-[2.5px] z-[60] pointer-events-none bg-transparent"
      >
        <div
          ref={progressBarRef}
          className="h-full w-full origin-left scale-x-0 bg-gradient-to-r from-[#2563EB] via-[#3B82F6] to-[#0F766E]"
        />
      </div>

      {/* GSAP ScrollSmoother Viewport Wrapper & Content Envelope */}
      <div id="smooth-wrapper" ref={wrapperRef} className="w-full min-h-screen">
        <div id="smooth-content" ref={contentRef} className="w-full min-h-screen">
          {children}
        </div>
      </div>

      {/* Floating Back-to-Top Control powered by ScrollSmoother */}
      {showBackToTop && (
        <button
          type="button"
          onClick={scrollToTop}
          aria-label="Scroll back to top"
          title="Back to top"
          className="fixed bottom-6 right-6 z-40 min-w-[44px] min-h-[44px] px-3.5 rounded-full bg-white/90 backdrop-blur-md text-slate-900 border border-slate-200 shadow-lg hover:bg-primary-600 hover:text-white hover:border-primary-600 transition-all duration-200 flex items-center gap-1.5 text-xs font-semibold cursor-pointer"
        >
          <ArrowUp className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">Top</span>
        </button>
      )}
    </SmoothScrollContext.Provider>
  );
};

