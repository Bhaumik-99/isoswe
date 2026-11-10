import React from 'react';
import { createPortal } from 'react-dom';

interface PortalProps {
  children: React.ReactNode;
}

/**
 * Renders overlays, modals, and drawers directly under document.body
 * so position:fixed layers remain anchored to the viewport cleanly
 * outside GSAP ScrollSmoother's transformed #smooth-content container.
 */
export const Portal: React.FC<PortalProps> = ({ children }) => {
  if (typeof document === 'undefined') {
    return <>{children}</>;
  }
  return createPortal(children, document.body);
};

