import React, { useRef, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useGSAP } from '@gsap/react';
import {
  Building2,
  Home,
  Receipt,
  CreditCard,
  LifeBuoy,
  Bell,
  UserCheck,
  Sparkles,
  LogOut,
  Menu,
  X,
  ChevronDown,
  FileText,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { Badge } from '../components/ui/Badge';
import { Portal } from '../components/ui/Portal';
import { FixedHeaderPortal } from '../components/motion/FixedHeaderPortal';
import { useGsapStagger } from '../components/motion/useGsapStagger';
import { NotificationBell } from '../features/notifications/NotificationBell';

gsap.registerPlugin(ScrollTrigger, useGSAP);

export const ResidentLayout: React.FC = () => {
  const { user, memberships, selectedFlat, setSelectedFlat, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [flatDropdownOpen, setFlatDropdownOpen] = useState(false);
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

  const navItems = [
    { name: 'My Flat Overview', path: '/resident/overview', icon: Home, exact: true },
    { name: 'Amenity Bookings', path: '/resident/amenities', icon: Sparkles },
    { name: 'Visitors & Gate Passes', path: '/resident/visitors', icon: UserCheck },
    { name: 'Maintenance Invoices', path: '/resident/billing', icon: Receipt },
    { name: 'Payment Receipts', path: '/resident/payments', icon: CreditCard },
    { name: 'Helpdesk & Requests', path: '/resident/complaints', icon: LifeBuoy },
    { name: 'Notifications', path: '/resident/notifications', icon: Bell },
    { name: 'Township Notices', path: '/resident/notices', icon: FileText },
  ];

  return (
    <div className="min-h-screen bg-[#f5f5f7] text-[#1d1d1f] flex flex-col">
      {/* Apple two-row fixed chrome portaled outside #smooth-wrapper */}
      <FixedHeaderPortal fallbackHeight={96}>
        <header className="w-full">
          {/* Row 1: global-nav (#000000, height 44px, 12px/400) */}
          <div className="w-full h-[44px] bg-[#000000] text-[#ffffff]">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-full flex items-center justify-between gap-3 text-[12px] font-normal tracking-[-0.12px]">
              <div className="flex items-center gap-2.5">
                <Building2 className="h-4 w-4 text-[#ffffff]" aria-hidden="true" />
                <span className="text-[#ffffff]">Marvel Greenfield</span>
              </div>

              <div className="flex items-center gap-3">
                <NotificationBell dark notificationsUrl="/resident/notifications" />

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

          {/* Row 2: sub-nav-frosted (#f5f5f7/80 backdrop-blur, height 52px, hairline bottom) */}
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
                  Resident Portal
                </span>
              </div>

              {/* Active Flat Selector Pill */}
              {selectedFlat && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setFlatDropdownOpen(!flatDropdownOpen)}
                    className="flex items-center gap-2 min-h-[36px] px-3.5 py-1 text-[14px] font-normal bg-[#ffffff] text-[#1d1d1f] rounded-full border border-[#e0e0e0] active:scale-95 transition-transform cursor-pointer"
                    aria-expanded={flatDropdownOpen}
                  >
                    <span className="font-mono font-semibold">
                      {selectedFlat.tower_number || 'Tower'}-{selectedFlat.flat_number || 'Unit'}
                    </span>
                    <Badge variant={selectedFlat.membership_type === 'OWNER' ? 'info' : 'neutral'}>
                      {selectedFlat.membership_type}
                    </Badge>
                    {memberships.length > 1 && <ChevronDown className="h-3.5 w-3.5 text-[#7a7a7a]" aria-hidden="true" />}
                  </button>

                  {flatDropdownOpen && memberships.length > 1 && (
                    <div className="absolute right-0 mt-2 w-60 bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] py-2 z-40 apple-product-shadow">
                      <div className="px-4 py-1.5 text-[12px] font-semibold text-[#7a7a7a] tracking-[-0.12px]">
                        Switch Active Unit
                      </div>
                      {memberships.map((m) => (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => {
                            setSelectedFlat(m);
                            setFlatDropdownOpen(false);
                          }}
                          className={`w-full text-left px-4 py-2.5 text-[14px] flex items-center justify-between hover:bg-[#f5f5f7] cursor-pointer ${
                            selectedFlat.id === m.id ? 'font-semibold text-[#0066cc]' : 'text-[#1d1d1f]'
                          }`}
                        >
                          <span className="font-mono">{m.tower_number}-{m.flat_number}</span>
                          <span className="text-[12px] text-[#7a7a7a]">{m.membership_type}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </header>
      </FixedHeaderPortal>

      {/* Main Body */}
      <div
        ref={bodyGridRef}
        className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full flex-1 flex gap-8 items-start"
      >
        {/* Desktop Sidebar Navigation */}
        <aside className="hidden md:block w-64 flex-shrink-0" aria-label="Resident portal navigation">
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
              aria-label="Mobile Navigation"
            >
              <div
                className="fixed inset-y-0 left-0 w-72 bg-[#ffffff] border-r border-[#e0e0e0] p-5 flex flex-col"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between pb-4 border-b border-[#e0e0e0]">
                  <span className="font-display text-[21px] font-semibold text-[#1d1d1f]">Resident Menu</span>
                  <button
                    type="button"
                    onClick={() => setMobileMenuOpen(false)}
                    aria-label="Close navigation menu"
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

        {/* Content View */}
        <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 outline-none">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
