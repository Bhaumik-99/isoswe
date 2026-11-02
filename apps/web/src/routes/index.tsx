import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { ProtectedRoute } from './ProtectedRoute';
import { AuthLayout } from '../layouts/AuthLayout';
import { ResidentLayout } from '../layouts/ResidentLayout';
import { StaffLayout } from '../layouts/StaffLayout';
import { LoginForm } from '../features/auth/LoginForm';
import { ResidentOverview } from '../features/resident/ResidentOverview';
import { StaffOverview } from '../features/staff/StaffOverview';
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
        <Route
          path="billing"
          element={
            <UpcomingModuleNotice
              moduleName="Maintenance Invoices & Ledger"
              plannedPhase="Phase 2 - Billing Engine"
              description="Automated monthly maintenance bill generation per apartment area (1,150 sq ft / ₹6.50 per sq ft + sinking fund formula)."
              deliverables={[
                'Multi-tenant invoice calculation engine',
                'Integer paise monetary precision to avoid floating-point errors',
                'Downloadable GST tax invoices in PDF format',
              ]}
            />
          }
        />
        <Route
          path="payments"
          element={
            <UpcomingModuleNotice
              moduleName="Digital Payment Collections"
              plannedPhase="Phase 2 - Payments"
              description="Seamless payment gateway integration supporting UPI, Netbanking, and Debit/Credit cards with instant receipt generation."
              deliverables={[
                'Payment gateway webhook verification with idempotent processing',
                'Automated instant receipt generation',
                'Society bank settlement tracking',
              ]}
            />
          }
        />
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
        <Route
          path="billing"
          element={
            <UpcomingModuleNotice
              moduleName="Society Batch Billing & Invoicing"
              plannedPhase="Phase 2 - Financial Operations"
              description="Trigger batch monthly billing across all 28 residential towers (2,400 flats) with automatic ledger adjustments."
              deliverables={[
                'Asynchronous billing-jobs SQS batch execution',
                'Defaulters interest calculation and penalty application',
              ]}
            />
          }
        />
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
