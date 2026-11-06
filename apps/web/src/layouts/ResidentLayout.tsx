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
  LogOut,
  Menu,
  X,
  ChevronDown,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { Badge } from '../components/ui/Badge';

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
    { name: 'Visitors & Gate Passes', path: '/resident/visitors', icon: UserCheck },
    { name: 'Maintenance Invoices', path: '/resident/billing', icon: Receipt },
    { name: 'Payment Receipts', path: '/resident/payments', icon: CreditCard },
    { name: 'Helpdesk & Requests', path: '/resident/complaints', icon: LifeBuoy },
    { name: 'Township Notices', path: '/resident/notices', icon: Bell },
  ];

  return (
    <div className="min-h-screen bg-[#fbfcfd] flex flex-col">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100"
              aria-label="Toggle Navigation Menu"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>

            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-600 text-white flex items-center justify-center font-bold">
                <Building2 className="h-5 w-5" />
              </div>
              <div>
                <span className="font-semibold text-sm text-slate-900 block leading-tight">
                  Marvel Greenfield
                </span>
                <span className="text-xs text-slate-500 block">Resident Portal</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Flat Selector Dropdown (for multi-flat residents) */}
            {selectedFlat && (
              <div className="relative">
                <button
                  onClick={() => setFlatDropdownOpen(!flatDropdownOpen)}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md border border-slate-200 transition-colors"
                >
                  <span>Flat: {selectedFlat.tower_number || 'Tower'}-{selectedFlat.flat_number || 'Unit'}</span>
                  <Badge variant={selectedFlat.membership_type === 'OWNER' ? 'success' : 'warning'}>
                    {selectedFlat.membership_type}
                  </Badge>
                  {memberships.length > 1 && <ChevronDown className="h-3.5 w-3.5 text-slate-500" />}
                </button>

                {flatDropdownOpen && memberships.length > 1 && (
                  <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-40">
                    <div className="px-3 py-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                      Switch Active Unit
                    </div>
                    {memberships.map((m) => (
                      <button
                        key={m.id}
                        onClick={() => {
                          setSelectedFlat(m);
                          setFlatDropdownOpen(false);
                        }}
                        className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-slate-50 ${
                          selectedFlat.id === m.id ? 'bg-indigo-50/70 font-semibold text-indigo-900' : 'text-slate-700'
                        }`}
                      >
                        <span>{m.tower_number}-{m.flat_number}</span>
                        <span className="text-[10px] uppercase text-slate-500">{m.membership_type}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* User Profile & Logout */}
            <div className="flex items-center gap-3 pl-3 border-l border-slate-200">
              <div className="hidden sm:block text-right">
                <div className="text-xs font-medium text-slate-900">{user?.full_name}</div>
                <div className="text-[11px] text-slate-500 truncate max-w-[140px]">{user?.email}</div>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100 transition-colors"
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
        {/* Desktop Sidebar Navigation */}
        <aside className="hidden md:block w-60 flex-shrink-0">
          <nav className="space-y-1 sticky top-24">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-700 font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`
                }
              >
                <item.icon className="h-4 w-4" />
                <span>{item.name}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="fixed inset-0 z-40 md:hidden bg-slate-900/40 backdrop-blur-sm" onClick={() => setMobileMenuOpen(false)}>
            <div
              className="fixed inset-y-0 left-0 w-64 bg-white p-4 shadow-xl flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between pb-4 border-b border-slate-200">
                <span className="font-semibold text-sm text-slate-900">Navigation</span>
                <button onClick={() => setMobileMenuOpen(false)}>
                  <X className="h-5 w-5 text-slate-500" />
                </button>
              </div>
              <nav className="mt-4 space-y-1 flex-1">
                {navItems.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    onClick={() => setMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium ${
                        isActive ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-slate-600'
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
