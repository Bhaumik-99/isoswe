import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { ProtectedRoute } from './ProtectedRoute';
import { AuthLayout } from '../layouts/AuthLayout';
import { ResidentLayout } from '../layouts/ResidentLayout';
import { StaffLayout } from '../layouts/StaffLayout';
import { LoginForm } from '../features/auth/LoginForm';
import { ResidentOverview } from '../features/resident/ResidentOverview';
import { ResidentBilling } from '../features/resident/ResidentBilling';
import { ResidentPayments } from '../features/resident/ResidentPayments';
import { ResidentComplaints } from '../features/resident/ResidentComplaints';
import { ResidentVisitorsPage } from '../features/resident/ResidentVisitorsPage';
import { StaffOverview } from '../features/staff/StaffOverview';
import { StaffBilling } from '../features/staff/StaffBilling';
import { StaffHelpdesk } from '../features/staff/StaffHelpdesk';
import { StaffReconciliation } from '../features/staff/reconciliation/StaffReconciliation';
import { ResidentsDirectory } from '../features/staff/residents/ResidentsDirectory';
import { CommitteeOverview } from '../features/committee/CommitteeOverview';
import { GateTabletPage } from '../features/gate/GateTabletPage';
import { UpcomingModuleNotice } from '../components/UpcomingModuleNotice';
import { NotFound } from '../components/NotFound';
import { LoadingScreen } from '../components/LoadingScreen';

const RootRedirect: React.FC = () => {
  const { isAuthenticated, isLoading, roles, permissions } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (roles.includes('RESIDENT')) {
    return <Navigate to="/resident/overview" replace />;
  }

  if (
    roles.includes('HELPDESK') &&
    permissions.includes('GATE_OPERATIONS') &&
    !permissions.includes('COMPLAINT_MANAGE')
  ) {
    return <Navigate to="/gate" replace />;
  }

  return <Navigate to="/staff/overview" replace />;
};

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />

      {/* Auth Portal */}
      <Route
        path="/login"
        element={
          <AuthLayout>
            <LoginForm />
          </AuthLayout>
        }
      />

      {/* Gate Tablet Security Operations Console */}
      <Route
        path="/gate"
        element={
          <ProtectedRoute allowedRoles={['HELPDESK']} requiredPermissions={['GATE_OPERATIONS']}>
            <GateTabletPage />
          </ProtectedRoute>
        }
      />

      {/* Resident Portal */}
      <Route
        path="/resident"
        element={
          <ProtectedRoute allowedRoles={['RESIDENT']}>
            <ResidentLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<ResidentOverview />} />
        <Route path="visitors" element={<ResidentVisitorsPage />} />
        <Route path="billing" element={<ResidentBilling />} />
        <Route path="payments" element={<ResidentPayments />} />
        <Route path="complaints" element={<ResidentComplaints />} />
        <Route
          path="notices"
          element={
            <UpcomingModuleNotice
              moduleName="Township Communications & Notices"
              plannedPhase="Phase 2 - Communications"
              description="Official federation circulars, power/water maintenance advisories, and emergency alerts."
              deliverables={[
                'Multi-tower targeted broadcasts',
                'SMS and email delivery via notification-jobs SQS queue',
              ]}
            />
          }
        />
      </Route>

      {/* Staff Operations Portal */}
      <Route
        path="/staff"
        element={
          <ProtectedRoute allowedRoles={['HELPDESK']}>
            <StaffLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<StaffOverview />} />
        <Route
          path="helpdesk"
          element={
            <ProtectedRoute requiredPermissions={['COMPLAINT_MANAGE']}>
              <StaffHelpdesk />
            </ProtectedRoute>
          }
        />
        <Route
          path="billing"
          element={
            <ProtectedRoute requiredPermissions={['BILLING_MANAGE']}>
              <StaffBilling />
            </ProtectedRoute>
          }
        />
        <Route
          path="reconciliation"
          element={
            <ProtectedRoute requiredPermissions={['RECONCILIATION_REVIEW']}>
              <StaffReconciliation />
            </ProtectedRoute>
          }
        />
        <Route path="residents" element={<ResidentsDirectory />} />
        <Route
          path="committee"
          element={
            <ProtectedRoute requiredPermissions={['COMMITTEE_REPORT_READ']}>
              <CommitteeOverview />
            </ProtectedRoute>
          }
        />
      </Route>

      <Route path="/committee" element={<Navigate to="/staff/committee" replace />} />

      {/* 404 Fallback */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
};
