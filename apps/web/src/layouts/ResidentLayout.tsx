import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
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
import { NotificationBell } from '../features/notifications/NotificationBell';

export const ResidentLayout: React.FC = () => {
  const { user, memberships, selectedFlat, setSelectedFlat, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [flatDropdownOpen, setFlatDropdownOpen] = useState(false);
  const navigate = useNavigate();

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
    <div className="min-h-screen bg-[#f6f5f4] text-[#000000] flex flex-col">
      {/* Top Header (Notion nav-bar) */}
      <header className="bg-[#ffffff] text-[#000000] border-b border-[#e6e6e6] sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 text-[#615d59] hover:text-[#000000] rounded-[5px] hover:bg-[#f6f5f4]"
              aria-label="Toggle Navigation Menu"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>

            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-[8px] bg-[#000000] text-[#ffffff] flex items-center justify-center font-bold border border-[#e6e6e6]">
                <Building2 className="h-4 w-4" />
              </div>
              <div>
                <span className="font-semibold text-[15px] text-[#000000] block leading-tight tracking-[-0.125px]">
                  Marvel Greenfield
                </span>
                <span className="text-[12px] text-[#615d59] block">Resident Workspace</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Flat Selector Dropdown (for multi-flat residents) */}
            {selectedFlat && (
              <div className="relative">
                <button
                  onClick={() => setFlatDropdownOpen(!flatDropdownOpen)}
                  className="flex items-center gap-2 px-3.5 py-1.5 text-[14px] font-medium bg-[#ffffff] hover:bg-[#f6f5f4] text-[#000000] rounded-[8px] border border-[#e6e6e6] transition-colors"
                >
                  <span>Flat: {selectedFlat.tower_number || 'Tower'}-{selectedFlat.flat_number || 'Unit'}</span>
                  <Badge variant={selectedFlat.membership_type === 'OWNER' ? 'success' : 'warning'}>
                    {selectedFlat.membership_type}
                  </Badge>
                  {memberships.length > 1 && <ChevronDown className="h-3.5 w-3.5 text-[#615d59]" />}
                </button>

                {flatDropdownOpen && memberships.length > 1 && (
                  <div className="absolute right-0 mt-2 w-56 bg-[#ffffff] border border-[#e6e6e6] rounded-[12px] shadow-md py-1 z-40">
                    <div className="px-3 py-1.5 text-[12px] font-semibold text-[#a39e98] tracking-[0.125px]">
                      Switch Active Unit
                    </div>
                    {memberships.map((m) => (
                      <button
                        key={m.id}
                        onClick={() => {
                          setSelectedFlat(m);
                          setFlatDropdownOpen(false);
                        }}
                        className={`w-full text-left px-3 py-2 text-[14px] flex items-center justify-between hover:bg-[#f6f5f4] ${
                          selectedFlat.id === m.id ? 'bg-[#f6f5f4] font-semibold text-[#0075de]' : 'text-[#31302e]'
                        }`}
                      >
                        <span>{m.tower_number}-{m.flat_number}</span>
                        <span className="text-[12px] text-[#615d59]">{m.membership_type}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Notification Bell */}
            <NotificationBell notificationsUrl="/resident/notifications" />

            {/* User Profile & Logout */}
            <div className="flex items-center gap-3 pl-3 border-l border-[#e6e6e6]">
              <div className="hidden sm:block text-right">
                <div className="text-[14px] font-medium text-[#000000] leading-tight">{user?.full_name}</div>
                <div className="text-[12px] text-[#615d59] truncate max-w-[140px]">{user?.email}</div>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 text-[#615d59] hover:text-[#000000] rounded-[8px] border border-transparent hover:border-[#e6e6e6] hover:bg-[#f6f5f4] transition-colors"
                title="Log out"
                aria-label="Log out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full flex-1 flex gap-8">
        {/* Desktop Sidebar Navigation (Notion ex-app-shell-row: rounded 5px, padding 8px 16px, body-sm 15px) */}
        <aside className="hidden md:block w-60 flex-shrink-0">
          <nav className="space-y-1 sticky top-24">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-2 rounded-[5px] text-[15px] leading-[1.33] transition-colors ${
                    isActive
                      ? 'bg-[#ffffff] text-[#0075de] font-semibold border border-[#e6e6e6] shadow-xs'
                      : 'text-[#615d59] font-normal hover:text-[#000000] hover:bg-[#ffffff]/70'
                  }`
                }
              >
                <item.icon className="h-4 w-4 flex-shrink-0" />
                <span>{item.name}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-40 md:hidden bg-black/30 backdrop-blur-[1px]" onClick={() => setMobileMenuOpen(false)}>
            <div
              className="fixed inset-y-0 left-0 w-64 bg-[#ffffff] border-r border-[#e6e6e6] p-4 shadow-lg flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between pb-4 border-b border-[#e6e6e6]">
                <span className="font-semibold text-[15px] text-[#000000]">Navigation</span>
                <button onClick={() => setMobileMenuOpen(false)}>
                  <X className="h-5 w-5 text-[#615d59]" />
                </button>
              </div>
              <nav className="mt-4 space-y-1 flex-1">
                {navItems.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-4 py-2 rounded-[5px] text-[15px] leading-[1.33] ${
                        isActive ? 'bg-[#f6f5f4] text-[#0075de] font-semibold' : 'text-[#615d59] hover:text-[#000000]'
                      }`
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    <span>{item.name}</span>
                  </NavLink>
                ))}
              </nav>
            </div>
          </div>
        )}

        {/* Content View */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
