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
import { StaffOverview } from '../features/staff/StaffOverview';
import { StaffBilling } from '../features/staff/StaffBilling';
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
        <Route
          path="complaints"
          element={
            <UpcomingModuleNotice
              moduleName="Facility Management Helpdesk & AI"
              plannedPhase="Phase 3 - AI Classification"
              description="Resident complaint lifecycle with automated Bedrock LLM categorization, urgency detection, and technician dispatch."
              deliverables={[
                'Asynchronous complaint-ai-jobs SQS queue integration',
                'SLA escalation tracking for 180 township facility employees',
                'Resident feedback and satisfaction surveys',
              ]}
            />
          }
        />
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
            <UpcomingModuleNotice
              moduleName="Facility Helpdesk Dispatch Center"
              plannedPhase="Phase 3 - Operations"
              description="Technician assignment queue, work order management, and resident maintenance resolution."
              deliverables={[
                'Work order generation and parts requisition',
                'Shift management for 180 facility staff',
              ]}
            />
          }
        />
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
