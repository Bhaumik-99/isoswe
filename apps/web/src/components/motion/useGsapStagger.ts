import { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

/**
 * Applies the UI/UX Pro Max staggered entrance reveal to elements matching `selector`
 * inside the returned container ref, automatically skipping motion under
 * `prefers-reduced-motion: reduce`.
 */
export function useGsapStagger<T extends HTMLElement = HTMLDivElement>(
  selector = '[data-gsap-stagger]',
  deps: unknown[] = []
) {
  const containerRef = useRef<T>(null);

  useGSAP(
    () => {
      if (typeof window === 'undefined' || !containerRef.current) return;
      const targets = containerRef.current.querySelectorAll(selector);
      if (!targets.length) return;

      const mm = gsap.matchMedia();
      mm.add('(prefers-reduced-motion: no-preference)', () => {
        gsap.fromTo(
          targets,
          { opacity: 0, y: 12, scale: 0.985 },
          {
            opacity: 1,
            y: 0,
            scale: 1,
            duration: 0.4,
            stagger: { each: 0.05, from: 'start' },
            ease: 'power2.out',
            clearProps: 'transform,opacity',
          }
        );
      });

      return () => mm.revert();
    },
    { scope: containerRef, dependencies: deps }
  );

  return containerRef;
}

