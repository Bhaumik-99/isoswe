import React from 'react';

export const LoadingScreen: React.FC<{ message?: string }> = ({
  message = 'Authenticating session...',
}) => {
  return (
    <div className="min-h-screen bg-[#fbfcfd] flex flex-col items-center justify-center p-4">
      <div className="flex flex-col items-center space-y-4">
        <div className="w-10 h-10 border-2 border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-600 tracking-wide">{message}</p>
      </div>
    </div>
  );
};
