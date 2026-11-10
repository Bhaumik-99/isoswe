import React from 'react';

export const LoadingScreen: React.FC<{ message?: string }> = ({
  message = 'Authenticating session...',
}) => {
  return (
    <div className="min-h-screen hero-mesh-bg flex flex-col items-center justify-center p-4">
      <div className="flex flex-col items-center space-y-4 bg-white/90 backdrop-blur-md px-8 py-7 rounded-2xl border border-slate-200 shadow-lg">
        <div
          aria-hidden="true"
          className="w-10 h-10 border-2 border-blue-100 border-t-primary-600 rounded-full animate-spin"
        />
        <p className="text-sm font-medium text-slate-700 tracking-wide">{message}</p>
      </div>
    </div>
  );
};
