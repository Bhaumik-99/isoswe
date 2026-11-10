import React from 'react';
import { Building2, CreditCard, KeyRound, ShieldCheck, Sparkles } from 'lucide-react';
import { useGsapStagger } from '../components/motion/useGsapStagger';

export const AuthLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const containerRef = useGsapStagger<HTMLDivElement>('[data-gsap-hero]');

  return (
    <div
      ref={containerRef}
      className="relative min-h-screen hero-mesh-bg text-slate-900 overflow-hidden flex flex-col justify-center py-10 sm:py-14 px-4 sm:px-6 lg:px-8"
    >
      {/* Ambient GSAP Parallax Mesh Highlights (decorative only) */}
      <div
        aria-hidden="true"
        data-speed="0.92"
        className="pointer-events-none absolute -top-28 -left-24 w-96 h-96 rounded-full bg-primary-500/10 blur-3xl"
      />
      <div
        aria-hidden="true"
        data-speed="0.88"
        className="pointer-events-none absolute -bottom-28 -right-24 w-[28rem] h-[28rem] rounded-full bg-teal-500/10 blur-3xl"
      />

      <main
        id="main-content"
        tabIndex={-1}
        className="relative z-10 w-full max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start outline-none"
      >
        {/* Left Column: Editorial Brand Hero & Capability Pillars */}
        <section
          aria-label="Platform Overview"
          className="lg:col-span-5 space-y-6 lg:sticky lg:top-12 pt-2 text-center lg:text-left"
        >
          <div
            data-gsap-hero
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full glass-surface border border-slate-200/90 shadow-xs text-xs font-semibold text-primary-700 tracking-wide"
          >
            <Sparkles className="w-3.5 h-3.5 text-accent" aria-hidden="true" />
            <span>Township Operations Workspace • Pune</span>
          </div>

          <div data-gsap-hero className="space-y-3">
            <div className="inline-flex lg:flex items-center justify-center lg:justify-start gap-3">
              <div className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-br from-primary-600 to-teal-700 text-white shadow-md shrink-0">
                <Building2 className="w-5 h-5" aria-hidden="true" />
              </div>
              <span className="text-xs font-mono uppercase tracking-widest text-slate-600 font-semibold">
                Marvel Greenfield
              </span>
            </div>

            <h1 className="font-display text-3xl sm:text-4xl lg:text-[42px] text-slate-900 leading-[1.12]">
              Marvel Greenfield Residences
            </h1>

            <p className="text-base text-slate-600 leading-relaxed max-w-lg mx-auto lg:mx-0">
              Unified society governance, billing reconciliation, visitor gate security, and resident self-service engineered for high-trust community operations.
            </p>
          </div>

          {/* Highlight Cards (3-5 key features pattern per UI/UX Pro Max) */}
          <div className="hidden sm:grid grid-cols-1 gap-3 text-left max-w-lg mx-auto lg:mx-0">
            <div
              data-gsap-hero
              className="glass-surface border border-slate-200/80 rounded-2xl p-4 shadow-xs flex items-start gap-3.5"
            >
              <div className="w-9 h-9 rounded-xl bg-blue-50 border border-blue-100 text-primary-600 flex items-center justify-center shrink-0">
                <CreditCard className="w-4 h-4" aria-hidden="true" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Transparent Billing &amp; Reconciliation</h2>
                <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
                  Automated maintenance invoices, UPI settlement tracking, and instant downloadable receipts.
                </p>
              </div>
            </div>

            <div
              data-gsap-hero
              className="glass-surface border border-slate-200/80 rounded-2xl p-4 shadow-xs flex items-start gap-3.5"
            >
              <div className="w-9 h-9 rounded-xl bg-teal-50 border border-teal-100 text-secondary flex items-center justify-center shrink-0">
                <KeyRound className="w-4 h-4" aria-hidden="true" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Offline-Resilient Gate Operations</h2>
                <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
                  Encrypted IndexedDB offline visitor queue, pre-approved guest passes, and multilingual security UI.
                </p>
              </div>
            </div>

            <div
              data-gsap-hero
              className="glass-surface border border-slate-200/80 rounded-2xl p-4 shadow-xs flex items-start gap-3.5"
            >
              <div className="w-9 h-9 rounded-xl bg-amber-50 border border-amber-100 text-accent flex items-center justify-center shrink-0">
                <ShieldCheck className="w-4 h-4" aria-hidden="true" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Committee Governance &amp; Audit Trails</h2>
                <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
                  Role-based flat scoping, real-time arrears ageing, and immutable administrative activity logs.
                </p>
              </div>
            </div>
          </div>

          <div
            data-gsap-hero
            className="flex items-center justify-center lg:justify-start gap-2 text-xs text-slate-600 pt-1"
          >
            <ShieldCheck className="h-4 w-4 text-secondary shrink-0" aria-hidden="true" />
            <span>Multi-tenant Isolation • Supabase Auth • End-to-End Auditing</span>
          </div>
        </section>

        {/* Right Column: Elevated Glassmorphic Authentication Card */}
        <section aria-label="Sign In Form" className="lg:col-span-7 w-full max-w-xl mx-auto lg:max-w-none">
          <div
            data-gsap-hero
            className="bg-white/95 backdrop-blur-xl py-6 px-5 sm:p-8 border border-slate-200/90 shadow-xl rounded-2xl"
          >
            {children}
          </div>
        </section>
      </main>
    </div>
  );
};
