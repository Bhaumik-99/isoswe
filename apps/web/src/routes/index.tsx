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
import { StaffOverview } from '../features/staff/StaffOverview';
import { StaffBilling } from '../features/staff/StaffBilling';
import { StaffHelpdesk } from '../features/staff/StaffHelpdesk';
import { CommitteeOverview } from '../features/committee/CommitteeOverview';
import { UpcomingModuleNotice } from '../components/UpcomingModuleNotice';
import { NotFound } from '../components/NotFound';
import { LoadingScreen } from '../components/LoadingScreen';

const RootRedirect: React.FC = () => {
  const { isAuthenticated, isLoading, roles } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (roles.includes('RESIDENT')) {
    return <Navigate to="/resident/overview" replace />;
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
        <Route path="helpdesk" element={<StaffHelpdesk />} />
        <Route path="billing" element={<StaffBilling />} />
        <Route
          path="reconciliation"
          element={
            <UpcomingModuleNotice
              moduleName="Automated Bank Statement Reconciliation"
              plannedPhase="Phase 3 - Financial Reconciliation"
              description="Upload society bank statements (CSV/MT940) with automated algorithmic transaction matching and suspense resolution."
              deliverables={[
                'Asynchronous reconciliation-jobs queue processing',
                'Automated NEFT/RTGS transaction reference matching',
                'Suspense account ledger workflow',
              ]}
            />
          }
        />
        <Route
          path="residents"
          element={
            <UpcomingModuleNotice
              moduleName="Township Resident & Unit Registry"
              plannedPhase="Phase 2 - Master Registry"
              description="Central registry of 2,400 flats across 28 towers, owner/tenant memberships, and move-in/move-out workflows."
              deliverables={[
                'Tenant lease verification and KYC documents store',
                'Vehicle parking RFID management',
              ]}
            />
          }
        />
        <Route path="committee" element={<CommitteeOverview />} />
      </Route>

      <Route path="/committee" element={<Navigate to="/staff/committee" replace />} />

      {/* 404 Fallback */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
};
