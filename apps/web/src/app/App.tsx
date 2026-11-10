import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../features/auth/AuthContext';
import { LanguageProvider } from '../i18n/LanguageContext';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { AppRoutes } from '../routes';
import { SmoothScrollProvider } from '../components/motion/SmoothScrollProvider';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
      refetchOnMount: 'always',
      staleTime: 0,
    },
  },
});

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <LanguageProvider>
          <AuthProvider>
            <BrowserRouter>
              <SmoothScrollProvider>
                <AppRoutes />
              </SmoothScrollProvider>
            </BrowserRouter>
          </AuthProvider>
        </LanguageProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
};
