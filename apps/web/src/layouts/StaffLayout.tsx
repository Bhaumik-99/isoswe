import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
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
import { NotificationBell } from '../features/notifications/NotificationBell';

export const StaffLayout: React.FC = () => {
  const { user, roles, permissions, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

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
              <div className="w-8 h-8 rounded-[8px] bg-[#0075de] text-[#ffffff] flex items-center justify-center font-bold border border-[#e6e6e6]">
                <ShieldAlert className="h-4 w-4" />
              </div>
              <div>
                <span className="font-semibold text-[15px] block leading-tight text-[#000000] tracking-[-0.125px]">
                  Township Operations
                </span>
                <span className="text-[12px] text-[#615d59] block">Facility &amp; Financial Workspace</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <Badge variant="info" className="uppercase font-mono text-[11px]">
              Role: {primaryRole}
            </Badge>

            <NotificationBell notificationsUrl="/staff/notifications" />

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

      {/* Main Layout Area */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full flex-1 flex gap-8">
        <aside className="hidden md:block w-64 flex-shrink-0">
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
            <div className="fixed inset-y-0 left-0 w-64 bg-[#ffffff] text-[#000000] border-r border-[#e6e6e6] p-4 shadow-lg flex flex-col" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between pb-4 border-b border-[#e6e6e6]">
                <span className="font-semibold text-[15px] text-[#000000]">Staff Navigation</span>
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

        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
