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
          start: 'top 116px',
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
    <div className="min-h-screen bg-[#f5f5f7] text-[#1d1d1f] flex flex-col">
      {/* Apple two-row fixed chrome portaled outside #smooth-wrapper */}
      <FixedHeaderPortal fallbackHeight={96}>
        <header className="w-full">
          {/* Row 1: global-nav (#000000, height 44px, 12px/400) */}
          <div className="w-full h-[44px] bg-[#000000] text-[#ffffff]">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-full flex items-center justify-between gap-3 text-[12px] font-normal tracking-[-0.12px]">
              <div className="flex items-center gap-2.5">
                <ShieldAlert className="h-4 w-4 text-[#ffffff]" aria-hidden="true" />
                <span className="text-[#ffffff]">Township Operations</span>
              </div>

              <div className="flex items-center gap-3">
                <NotificationBell dark notificationsUrl="/staff/notifications" />

                <span className="hidden sm:inline text-[#cccccc] truncate max-w-[180px]">
                  {user?.full_name}
                </span>

                <button
                  type="button"
                  onClick={handleLogout}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-[8px] bg-[#1d1d1f] text-[#ffffff] text-[12px] tracking-[-0.12px] active:scale-95 transition-transform cursor-pointer"
                  title="Log out"
                  aria-label="Log out"
                >
                  <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="hidden sm:inline">Sign Out</span>
                </button>
              </div>
            </div>
          </div>

          {/* Row 2: sub-nav-frosted (#f5f5f7/80 backdrop-blur, height 52px) */}
          <div className="w-full h-[52px] apple-subnav-frosted border-b border-[#e0e0e0] text-[#1d1d1f]">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-full flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="md:hidden w-[44px] h-[44px] flex items-center justify-center text-[#1d1d1f] rounded-full bg-[#d2d2d7]/65 active:scale-95 transition-transform cursor-pointer"
                  aria-label="Toggle Navigation Menu"
                  aria-expanded={mobileMenuOpen}
                >
                  {mobileMenuOpen ? <X className="h-4 w-4" aria-hidden="true" /> : <Menu className="h-4 w-4" aria-hidden="true" />}
                </button>

                <span className="font-display text-[21px] font-semibold tracking-[0.231px] leading-[1.19] text-[#1d1d1f]">
                  Operations Console
                </span>
              </div>

              <Badge variant="info" className="uppercase font-mono text-[11px]">
                Role: {primaryRole}
              </Badge>
            </div>
          </div>
        </header>
      </FixedHeaderPortal>

      {/* Main Layout Area */}
      <div
        ref={bodyGridRef}
        className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full flex-1 flex gap-8 items-start"
      >
        <aside className="hidden md:block w-64 flex-shrink-0" aria-label="Staff portal navigation">
          <nav ref={sidebarNavRef} className="space-y-1 w-64">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                data-gsap-nav
                className={({ isActive }) =>
                  `flex items-center gap-3 min-h-[44px] px-4 py-2.5 rounded-[11px] text-[14px] tracking-[-0.224px] transition-colors cursor-pointer ${
                    isActive
                      ? 'bg-[#ffffff] text-[#0066cc] font-semibold border border-[#e0e0e0]'
                      : 'text-[#333333] font-normal hover:text-[#1d1d1f] hover:bg-[#ffffff]/70 border border-transparent'
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
              className="fixed inset-0 z-50 md:hidden bg-[#000000]/45 backdrop-blur-sm"
              onClick={() => setMobileMenuOpen(false)}
              role="dialog"
              aria-modal="true"
              aria-label="Staff Mobile Navigation"
            >
              <div
                className="fixed inset-y-0 left-0 w-72 bg-[#ffffff] text-[#1d1d1f] border-r border-[#e0e0e0] p-5 flex flex-col"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between pb-4 border-b border-[#e0e0e0]">
                  <span className="font-display text-[21px] font-semibold text-[#1d1d1f]">Staff Navigation</span>
                  <button
                    type="button"
                    onClick={() => setMobileMenuOpen(false)}
                    aria-label="Close staff navigation"
                    className="w-[44px] h-[44px] flex items-center justify-center rounded-full bg-[#d2d2d7]/65 text-[#1d1d1f] active:scale-95 cursor-pointer"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
                <nav className="mt-4 space-y-1.5 flex-1 overflow-y-auto">
                  {navItems.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      className={({ isActive }) =>
                        `flex items-center gap-3 min-h-[44px] px-4 py-2.5 rounded-[11px] text-[14px] ${
                          isActive
                            ? 'bg-[#f5f5f7] text-[#0066cc] font-semibold border border-[#e0e0e0]'
                            : 'text-[#333333] font-normal hover:bg-[#f5f5f7]'
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
