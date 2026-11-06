import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { PermissionType, RoleType } from '../types';
import { LoadingScreen } from '../components/LoadingScreen';
import { Alert } from '../components/ui/Alert';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: RoleType[];
  requiredPermissions?: PermissionType[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  allowedRoles,
  requiredPermissions,
}) => {
  const { isAuthenticated, isLoading, roles, permissions } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen message="Verifying session credentials..." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && allowedRoles.length > 0) {
    const hasRole = allowedRoles.some((r) => roles.includes(r));
    if (!hasRole) {
      return (
        <div className="max-w-md mx-auto my-12 p-4">
          <Alert variant="error" title="Access Denied">
            You do not have the necessary permissions ({allowedRoles.join(', ')}) to access this portal section.
          </Alert>
        </div>
      );
    }
  }

  if (requiredPermissions && requiredPermissions.length > 0) {
    const hasPermissions = requiredPermissions.every((p) => permissions.includes(p));
    if (!hasPermissions) {
      return (
        <div className="max-w-md mx-auto my-12 p-4">
          <Alert variant="error" title="Access Denied">
            You do not have the necessary permissions ({requiredPermissions.join(', ')}) to access this portal section.
          </Alert>
        </div>
      );
    }
  }

  return <>{children}</>;
};
