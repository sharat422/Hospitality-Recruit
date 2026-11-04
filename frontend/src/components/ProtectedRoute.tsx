/**
 * Protected Route Component
 * Wraps routes that require authentication
 * Redirects to login if not authenticated
 */

import { Loader } from 'lucide-react';
import React from 'react';
import { Navigate,useLocation } from 'react-router-dom';
import { useAuth } from '../lib/AuthContext';
import { useRBAC } from '../lib/RBACContext';
import LanguageGate from './LanguageGate';

interface ProtectedRouteProps {
  children: React.ReactNode;
  permission?: string;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, permission }) => {
  const { user, isLoading, isAuthenticated } = useAuth();
  const { can, loading: accessLoading, error: accessError } = useRBAC();
  const location = useLocation();

  if (isLoading || (isAuthenticated && accessLoading)) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center space-y-4">
          <Loader className="w-8 h-8 animate-spin mx-auto text-purple-600" />
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }

  if (accessError) {
    return <div className="flex min-h-screen items-center justify-center p-6 text-center text-red-700">{accessError}</div>;
  }

  if (permission && !can(permission)) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
        <section className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 text-center shadow-sm">
          <h1 className="text-xl font-semibold text-gray-900">Access restricted</h1>
          <p className="mt-2 text-sm text-gray-600">
            Your assigned role does not include permission to open this page.
          </p>
          <a href="/" className="mt-5 inline-flex min-h-11 items-center text-sm font-medium text-purple-700 hover:text-purple-900">
            Return to home
          </a>
        </section>
      </main>
    );
  }

  // One wrap here covers every signed-in screen, including the employee PWA
  // at /employee-app, which does not use AppLayout. Public candidate routes
  // are not wrapped by ProtectedRoute, so recruiting is unaffected.
  return <LanguageGate>{children}</LanguageGate>;
};
