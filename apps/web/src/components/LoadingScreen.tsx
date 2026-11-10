import React from 'react';

export const LoadingScreen: React.FC<{ message?: string }> = ({
  message = 'Authenticating session...',
}) => {
  return (
    <div className="min-h-screen bg-[#ffffff] flex flex-col items-center justify-center p-4">
      <div className="flex flex-col items-center space-y-4 bg-[#f5f5f7] px-10 py-8 rounded-[18px] border border-[#e0e0e0]">
        <div
          aria-hidden="true"
          className="w-9 h-9 border-2 border-[#e0e0e0] border-t-[#0066cc] rounded-full animate-spin"
        />
        <p className="text-[14px] font-normal text-[#333333] tracking-[-0.224px]">{message}</p>
      </div>
    </div>
  );
};
