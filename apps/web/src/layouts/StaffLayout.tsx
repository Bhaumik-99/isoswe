import React, { useRef, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useGSAP } from '@gsap/react';
import {
  ShieldAlert,
  Headphones,
  CircleDollarSign,
  Scale,
  Users,
  Cpu,
  ShieldCheck,
  LogOut,
  Menu,
  X,
  Bell,
  Building2,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { Badge } from '../components/ui/Badge';
import { Portal } from '../components/ui/Portal';
import { FixedHeaderPortal } from '../components/motion/FixedHeaderPortal';
import { useGsapStagger } from '../components/motion/useGsapStagger';
import { NotificationBell } from '../features/notifications/NotificationBell';

gsap.registerPlugin(ScrollTrigger, useGSAP);

export const StaffLayout: React.FC = () => {
  const { user, roles, permissions, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  const bodyGridRef = useGsapStagger<HTMLDivElement>('[data-gsap-nav]');
  const sidebarNavRef = useRef<HTMLElement>(null);

  useGSAP(
    () => {
      if (typeof window === 'undefined' || !bodyGridRef.current || !sidebarNavRef.current) return;
      const mm = gsap.matchMedia();

      mm.add('(min-width: 768px) and (prefers-reduced-motion: no-preference)', () => {
        ScrollTrigger.create({
          trigger: bodyGridRef.current!,
          start: 'top 88px',
          end: () => {
            const totalH = bodyGridRef.current?.offsetHeight || 0;
            const navH = sidebarNavRef.current?.offsetHeight || 0;
            return `+=${Math.max(0, totalH - navH - 24)}`;
          },
          pin: sidebarNavRef.current!,
          pinSpacing: false,
          invalidateOnRefresh: true,
        });
      });

      return () => mm.revert();
    },
    { scope: bodyGridRef }
  );

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isHelpdesk = roles.includes('HELPDESK');
  const canManageComplaints = isHelpdesk && permissions.includes('COMPLAINT_MANAGE');
  const canReviewReconciliation = isHelpdesk && permissions.includes('RECONCILIATION_REVIEW');
  const canViewCommitteeReport = isHelpdesk && permissions.includes('COMMITTEE_REPORT_READ');
  const canOperateGate = isHelpdesk && permissions.includes('GATE_OPERATIONS');

  const navItems = [
    { name: 'Operations Overview', path: '/staff/overview', icon: Cpu, exact: true },
    ...(canOperateGate
      ? [{ name: 'Gate Operations Console', path: '/gate', icon: ShieldCheck }]
      : []),
    ...(canManageComplaints
      ? [{ name: 'Helpdesk Tickets', path: '/staff/helpdesk', icon: Headphones }]
      : []),
    ...(canReviewReconciliation
      ? [{ name: 'Bank Reconciliation', path: '/staff/reconciliation', icon: Scale }]
      : []),
    ...(canViewCommitteeReport
      ? [{ name: 'Committee Dashboard', path: '/staff/committee', icon: CircleDollarSign }]
      : []),
    { name: 'Amenity Operations', path: '/staff/amenities', icon: Building2 },
    { name: 'Residents Directory', path: '/staff/residents', icon: Users },
    { name: 'Notices & Deliveries', path: '/staff/notifications', icon: Bell },
  ];

  const primaryRole = roles[0] || 'STAFF';

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 flex flex-col">
      {/* Glassmorphic Top Header portaled outside #smooth-wrapper */}
      <FixedHeaderPortal fallbackHeight={65}>
        <header className="glass-surface border-b border-slate-200/80 shadow-xs text-slate-900">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="md:hidden min-w-[44px] min-h-[44px] flex items-center justify-center text-slate-600 hover:text-slate-900 rounded-xl hover:bg-slate-100 cursor-pointer"
                aria-label="Toggle Navigation Menu"
                aria-expanded={mobileMenuOpen}
              >
                {mobileMenuOpen ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
              </button>

              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-600 to-blue-800 text-white flex items-center justify-center shadow-xs shrink-0">
                  <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                </div>
                <div>
                  <span className="font-display text-base block leading-tight text-slate-900">
                    Township Operations
                  </span>
                  <span className="text-xs text-slate-600 block font-medium">Facility &amp; Financial Workspace</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              <Badge variant="info" className="uppercase font-mono text-[11px] hidden sm:inline-flex">
                Role: {primaryRole}
              </Badge>

              <NotificationBell notificationsUrl="/staff/notifications" />

              <div className="flex items-center gap-2.5 pl-2.5 border-l border-slate-200">
                <div className="hidden sm:block text-right">
                  <div className="text-sm font-medium text-slate-900 leading-tight">{user?.full_name}</div>
                  <div className="text-xs text-slate-600 truncate max-w-[140px]">{user?.email}</div>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="min-w-[44px] min-h-[44px] flex items-center justify-center text-slate-600 hover:text-red-700 rounded-xl border border-transparent hover:border-red-200 hover:bg-red-50 transition-colors cursor-pointer"
                  title="Log out"
                  aria-label="Log out"
                >
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>
        </header>
      </FixedHeaderPortal>

      {/* Main Layout Area */}
      <div
        ref={bodyGridRef}
        className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full flex-1 flex gap-8 items-start"
      >
        <aside className="hidden md:block w-64 flex-shrink-0" aria-label="Staff portal navigation">
          <nav ref={sidebarNavRef} className="space-y-1.5 w-64">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                data-gsap-nav
                className={({ isActive }) =>
                  `flex items-center gap-3 min-h-[44px] px-3.5 py-2.5 rounded-xl text-sm transition-all cursor-pointer ${
                    isActive
                      ? 'bg-white text-primary-700 font-semibold border border-blue-200/80 border-l-4 border-l-primary-600 shadow-xs'
                      : 'text-slate-600 font-medium hover:text-slate-900 hover:bg-white/80 hover:border-slate-200/60 border border-transparent'
                  }`
                }
              >
                <item.icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                <span>{item.name}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Mobile Navigation Drawer Portaled outside #smooth-wrapper */}
        {mobileMenuOpen && (
          <Portal>
            <div
              className="fixed inset-0 z-50 md:hidden bg-slate-900/40 backdrop-blur-xs"
              onClick={() => setMobileMenuOpen(false)}
              role="dialog"
              aria-modal="true"
              aria-label="Staff Mobile Navigation"
            >
              <div
                className="fixed inset-y-0 left-0 w-72 bg-white text-slate-900 border-r border-slate-200 p-4 shadow-2xl flex flex-col"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between pb-4 border-b border-slate-200">
                  <span className="font-display text-base text-slate-900">Staff Navigation</span>
                  <button
                    type="button"
                    onClick={() => setMobileMenuOpen(false)}
                    aria-label="Close staff navigation"
                    className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-xl text-slate-600 hover:bg-slate-100 cursor-pointer"
                  >
                    <X className="h-5 w-5" aria-hidden="true" />
                  </button>
                </div>
                <nav className="mt-4 space-y-1.5 flex-1 overflow-y-auto">
                  {navItems.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      className={({ isActive }) =>
                        `flex items-center gap-3 min-h-[44px] px-3.5 py-2.5 rounded-xl text-sm ${
                          isActive
                            ? 'bg-blue-50 text-primary-700 font-semibold border border-blue-200'
                            : 'text-slate-700 font-medium hover:bg-slate-50'
                        }`
                      }
                    >
                      <item.icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                      <span>{item.name}</span>
                    </NavLink>
                  ))}
                </nav>
              </div>
            </div>
          </Portal>
        )}

        <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 outline-none">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
