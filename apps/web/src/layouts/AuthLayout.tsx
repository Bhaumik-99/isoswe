import React from 'react';
import { Building2, ChevronRight, ShieldCheck } from 'lucide-react';
import { FixedHeaderPortal } from '../components/motion/FixedHeaderPortal';
import { useSmoothScroll } from '../components/motion/SmoothScrollContext';
import { useGsapStagger } from '../components/motion/useGsapStagger';

export const AuthLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { scrollTo } = useSmoothScroll();
  const galleryRef = useGsapStagger<HTMLDivElement>('[data-gsap-gallery]');

  return (
    <div ref={galleryRef} className="min-h-screen bg-[#ffffff] text-[#1d1d1f] flex flex-col">
      {/* Apple two-row header: 44px pure-black global-nav + 52px frosted parchment sub-nav */}
      <FixedHeaderPortal fallbackHeight={96}>
        <div className="w-full">
          <nav
            aria-label="Global Navigation"
            className="w-full h-[44px] bg-[#000000] text-[#ffffff]"
          >
            <div className="max-w-[980px] mx-auto px-4 sm:px-6 h-full flex items-center justify-between text-[12px] font-normal tracking-[-0.12px]">
              <button
                type="button"
                onClick={() => scrollTo(0, true)}
                className="flex items-center gap-2 text-[#ffffff] cursor-pointer active:scale-95 transition-transform"
              >
                <Building2 className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Marvel Greenfield</span>
              </button>

              <div className="hidden sm:flex items-center gap-5 text-[#cccccc]">
                <button
                  type="button"
                  onClick={() => scrollTo('#login-workspace', true)}
                  className="hover:text-[#ffffff] transition-colors cursor-pointer"
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => scrollTo('#tile-finance', true)}
                  className="hover:text-[#ffffff] transition-colors cursor-pointer"
                >
                  Finance
                </button>
                <button
                  type="button"
                  onClick={() => scrollTo('#tile-gate', true)}
                  className="hover:text-[#ffffff] transition-colors cursor-pointer"
                >
                  Gate Security
                </button>
                <button
                  type="button"
                  onClick={() => scrollTo('#tile-footer', true)}
                  className="hover:text-[#ffffff] transition-colors cursor-pointer"
                >
                  Architecture
                </button>
              </div>

              <button
                type="button"
                onClick={() => scrollTo('#login-workspace', true)}
                className="px-[15px] py-[4px] rounded-[8px] bg-[#1d1d1f] text-[#ffffff] text-[12px] font-normal tracking-[-0.12px] active:scale-95 transition-transform cursor-pointer"
              >
                Access
              </button>
            </div>
          </nav>

          <div className="w-full h-[52px] apple-subnav-frosted border-b border-[#e0e0e0] text-[#1d1d1f]">
            <div className="max-w-[980px] mx-auto px-4 sm:px-6 h-full flex items-center justify-between">
              <span className="font-display text-[21px] font-semibold tracking-[0.231px] leading-[1.19] text-[#1d1d1f]">
                Township Workspace
              </span>

              <div className="flex items-center gap-4">
                <span className="hidden md:inline text-[12px] text-[#333333] tracking-[-0.12px]">
                  Pune Residential Operations
                </span>
                <button
                  type="button"
                  onClick={() => scrollTo('#login-workspace', true)}
                  className="px-3.5 py-1 rounded-full bg-[#0066cc] text-[#ffffff] text-[12px] font-normal tracking-[-0.12px] active:scale-95 transition-transform cursor-pointer"
                >
                  Sign In
                </button>
              </div>
            </div>
          </div>
        </div>
      </FixedHeaderPortal>

      <main id="main-content" tabIndex={-1} className="flex-1 outline-none">
        {/* TILE 1: Full-Bleed White Product Tile + Artifact Card resting on surface */}
        <section className="w-full bg-[#ffffff] text-[#1d1d1f] pt-12 sm:pt-16 pb-20 px-4 sm:px-6">
          <div className="max-w-[980px] mx-auto text-center space-y-3">
            <h1
              data-gsap-gallery
              className="font-display text-[34px] sm:text-[40px] lg:text-[56px] font-semibold leading-[1.07] tracking-[-0.28px] text-[#1d1d1f]"
            >
              Marvel Greenfield Residences
            </h1>
            <p
              data-gsap-gallery
              className="font-display text-[21px] sm:text-[28px] font-normal leading-[1.14] tracking-[0.196px] text-[#1d1d1f] max-w-2xl mx-auto"
            >
              Society governance, maintenance finance, and gate security. All in one quiet system.
            </p>

            <div
              data-gsap-gallery
              className="pt-3 flex flex-wrap items-center justify-center gap-4"
            >
              <button
                type="button"
                onClick={() => scrollTo('#login-workspace', true)}
                className="px-[22px] py-[11px] rounded-full bg-[#0066cc] text-[#ffffff] text-[17px] font-normal tracking-[-0.374px] active:scale-95 transition-transform cursor-pointer"
              >
                Sign In to Portal
              </button>
              <button
                type="button"
                onClick={() => scrollTo('#tile-finance', true)}
                className="px-[22px] py-[11px] rounded-full bg-[#ffffff] text-[#0066cc] border border-[#0066cc] text-[17px] font-normal tracking-[-0.374px] active:scale-95 transition-transform cursor-pointer"
              >
                Explore Modules
              </button>
            </div>
          </div>

          {/* Product Artifact Card with the ONE signature Apple drop-shadow resting on the light tile */}
          <div
            id="login-workspace"
            data-gsap-gallery
            className="max-w-[660px] mx-auto mt-10 sm:mt-12 bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] p-6 sm:p-8 apple-product-shadow"
          >
            {children}
          </div>
        </section>

        {/* TILE 2: Full-Bleed Dark Tile 1 (#272729) — Edge-to-edge color break, zero border */}
        <section
          id="tile-finance"
          data-speed="0.98"
          className="w-full bg-[#272729] text-[#ffffff] py-[80px] px-4 sm:px-6"
        >
          <div className="max-w-[980px] mx-auto text-center space-y-3">
            <h2 className="font-display text-[34px] sm:text-[40px] font-semibold leading-[1.1] tracking-normal text-[#ffffff]">
              Financial Ledger.
            </h2>
            <p className="font-display text-[21px] sm:text-[28px] font-normal leading-[1.14] tracking-[0.196px] text-[#cccccc]">
              Maintenance billing, UPI reconciliation, and official receipts. Built without noise.
            </p>
            <div className="pt-2">
              <button
                type="button"
                onClick={() => scrollTo('#login-workspace', true)}
                className="inline-flex items-center gap-1 text-[17px] text-[#2997ff] hover:underline cursor-pointer"
              >
                <span>Open Resident &amp; Finance Sign In</span>
                <ChevronRight className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-10 text-left">
              <div className="bg-[#2a2a2c] rounded-[18px] p-6 space-y-2">
                <h3 className="font-display text-[21px] font-semibold text-[#ffffff] tracking-[0.231px]">
                  Zero Duplicate Charges
                </h3>
                <p className="text-[14px] text-[#cccccc] leading-[1.43] tracking-[-0.224px]">
                  Idempotent monthly assessment runs ensure one verified invoice per flat and billing period.
                </p>
              </div>
              <div className="bg-[#252527] rounded-[18px] p-6 space-y-2">
                <h3 className="font-display text-[21px] font-semibold text-[#ffffff] tracking-[0.231px]">
                  Bank Statement Matching
                </h3>
                <p className="text-[14px] text-[#cccccc] leading-[1.43] tracking-[-0.224px]">
                  VPA resolution and manual review queues settle collections directly against invoice balances.
                </p>
              </div>
              <div className="bg-[#2a2a2c] rounded-[18px] p-6 space-y-2">
                <h3 className="font-display text-[21px] font-semibold text-[#ffffff] tracking-[0.231px]">
                  Committee Oversight
                </h3>
                <p className="text-[14px] text-[#cccccc] leading-[1.43] tracking-[-0.224px]">
                  Real-time tower arrears ageing, SLA accountability, and read-only audit exports.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* TILE 3: Full-Bleed Parchment Tile (#f5f5f7) */}
        <section
          id="tile-gate"
          className="w-full bg-[#f5f5f7] text-[#1d1d1f] py-[80px] px-4 sm:px-6"
        >
          <div className="max-w-[980px] mx-auto text-center space-y-3">
            <h2 className="font-display text-[34px] sm:text-[40px] font-semibold leading-[1.1] tracking-normal text-[#1d1d1f]">
              Gate Perimeter.
            </h2>
            <p className="font-display text-[21px] sm:text-[28px] font-normal leading-[1.14] tracking-[0.196px] text-[#333333]">
              Encrypted offline visitor queues and instant guest pass check-in.
            </p>
            <div className="pt-2">
              <button
                type="button"
                onClick={() => scrollTo('#login-workspace', true)}
                className="inline-flex items-center gap-1 text-[17px] text-[#0066cc] hover:underline cursor-pointer"
              >
                <span>Try Gate Security Role</span>
                <ChevronRight className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-10 text-left">
              <div className="bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] p-6 space-y-2">
                <h3 className="text-[17px] font-semibold text-[#1d1d1f] tracking-[-0.374px]">
                  AES-GCM Offline Sync
                </h3>
                <p className="text-[14px] text-[#333333] leading-[1.43] tracking-[-0.224px]">
                  Visitor logs stay encrypted in IndexedDB during gate network drops and sync cleanly on reconnect.
                </p>
              </div>
              <div className="bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] p-6 space-y-2">
                <h3 className="text-[17px] font-semibold text-[#1d1d1f] tracking-[-0.374px]">
                  Multilingual Security UI
                </h3>
                <p className="text-[14px] text-[#333333] leading-[1.43] tracking-[-0.224px]">
                  Instant switching across English, Hindi, and Marathi for fast gatehouse tablet workflows.
                </p>
              </div>
              <div className="bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] p-6 space-y-2">
                <h3 className="text-[17px] font-semibold text-[#1d1d1f] tracking-[-0.374px]">
                  90-Day Data Retention
                </h3>
                <p className="text-[14px] text-[#333333] leading-[1.43] tracking-[-0.224px]">
                  Time-limited presigned photo URLs paired with automated privacy notices and retention policies.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Apple Footer (#f5f5f7 parchment, 64px vertical padding, 17px/2.41 dense-link rhythm, 12px fine-print) */}
        <footer
          id="tile-footer"
          className="w-full bg-[#f5f5f7] border-t border-[#e0e0e0] text-[#333333] py-[64px] px-4 sm:px-6"
        >
          <div className="max-w-[980px] mx-auto space-y-8">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-6 pb-8 border-b border-[#e0e0e0]">
              <div>
                <h4 className="text-[14px] font-semibold text-[#1d1d1f] tracking-[-0.224px] mb-1">
                  Portals
                </h4>
                <ul className="text-[17px] font-normal leading-[2.41] text-[#333333]">
                  <li>
                    <button
                      type="button"
                      onClick={() => scrollTo('#login-workspace', true)}
                      className="hover:text-[#0066cc] cursor-pointer"
                    >
                      Resident Portal
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => scrollTo('#login-workspace', true)}
                      className="hover:text-[#0066cc] cursor-pointer"
                    >
                      Staff &amp; Finance
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => scrollTo('#login-workspace', true)}
                      className="hover:text-[#0066cc] cursor-pointer"
                    >
                      Gate Console
                    </button>
                  </li>
                </ul>
              </div>

              <div>
                <h4 className="text-[14px] font-semibold text-[#1d1d1f] tracking-[-0.224px] mb-1">
                  Governance
                </h4>
                <ul className="text-[17px] font-normal leading-[2.41] text-[#333333]">
                  <li>Managing Committee</li>
                  <li>Arrears &amp; Ageing</li>
                  <li>Notice Deliveries</li>
                </ul>
              </div>

              <div>
                <h4 className="text-[14px] font-semibold text-[#1d1d1f] tracking-[-0.224px] mb-1">
                  Trust &amp; Security
                </h4>
                <ul className="text-[17px] font-normal leading-[2.41] text-[#333333]">
                  <li>Multi-tenant Isolation</li>
                  <li>Supabase Auth</li>
                  <li>End-to-End Auditing</li>
                </ul>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-[12px] text-[#7a7a7a] tracking-[-0.12px]">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#0066cc]" aria-hidden="true" />
                <span>Marvel Greenfield Co-operative Housing Society • Pune</span>
              </div>
              <span>Society Operations Platform</span>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
};
