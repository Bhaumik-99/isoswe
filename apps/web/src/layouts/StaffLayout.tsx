import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  ShieldAlert,
  Headphones,
  CircleDollarSign,
  Scale,
  Users,
  Cpu,
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { Badge } from '../components/ui/Badge';

export const StaffLayout: React.FC = () => {
  const { user, roles, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isFinance = roles.includes('FINANCE') || roles.includes('PLATFORM_ADMIN');
  const isHelpdesk = roles.includes('HELPDESK') || roles.includes('PLATFORM_ADMIN');

  const navItems = [
    { name: 'Operations Overview', path: '/staff/overview', icon: Cpu, exact: true },
    ...(isHelpdesk
      ? [{ name: 'Helpdesk Tickets', path: '/staff/helpdesk', icon: Headphones }]
      : []),
    ...(isFinance
      ? [
          { name: 'Billing & Invoicing', path: '/staff/billing', icon: CircleDollarSign },
          { name: 'Bank Reconciliation', path: '/staff/reconciliation', icon: Scale },
        ]
      : []),
    { name: 'Residents Directory', path: '/staff/residents', icon: Users },
  ];

  const primaryRole = roles[0] || 'STAFF';

  return (
    <div className="min-h-screen bg-[#fbfcfd] flex flex-col">
      {/* Top Header */}
      <header className="bg-slate-900 text-white sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 text-slate-300 hover:text-white rounded-lg hover:bg-slate-800"
              aria-label="Toggle Navigation Menu"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>

            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-500 text-white flex items-center justify-center font-bold">
                <ShieldAlert className="h-5 w-5" />
              </div>
              <div>
                <span className="font-semibold text-sm block leading-tight text-white">
                  Township Operations
                </span>
                <span className="text-xs text-slate-400 block">Facility & Financial Ops</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <Badge variant="info" className="uppercase font-mono text-[11px] bg-slate-800 text-indigo-300 border-slate-700">
              Role: {primaryRole}
            </Badge>

            <div className="flex items-center gap-3 pl-3 border-l border-slate-700">
              <div className="hidden sm:block text-right">
                <div className="text-xs font-medium text-white">{user?.full_name}</div>
                <div className="text-[11px] text-slate-400 truncate max-w-[140px]">{user?.email}</div>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                title="Log out"
                aria-label="Log out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Layout Area */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full flex-1 flex gap-8">
        <aside className="hidden md:block w-64 flex-shrink-0">
          <nav className="space-y-1 sticky top-24">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-slate-900 text-white font-semibold'
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
            <div className="fixed inset-y-0 left-0 w-64 bg-slate-900 text-white p-4 shadow-xl flex flex-col" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <span className="font-semibold text-sm">Staff Navigation</span>
                <button onClick={() => setMobileMenuOpen(false)}>
                  <X className="h-5 w-5 text-slate-400" />
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
                        isActive ? 'bg-indigo-600 text-white font-semibold' : 'text-slate-300 hover:bg-slate-800'
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

        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
