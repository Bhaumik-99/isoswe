import React from 'react';
import { Building2, ShieldCheck } from 'lucide-react';

export const AuthLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="min-h-screen bg-[#f6f5f4] text-[#000000] flex flex-col justify-center py-10 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-lg text-center px-4 sm:px-0">
        {/* Decorative Notion Sticker Dots */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white border border-[#e6e6e6] mb-4">
          <span className="w-2 h-2 rounded-full bg-[#62aef0]" />
          <span className="w-2 h-2 rounded-full bg-[#ff64c8]" />
          <span className="w-2 h-2 rounded-full bg-[#dd5b00]" />
          <span className="w-2 h-2 rounded-full bg-[#1aae39]" />
          <span className="text-[12px] font-semibold tracking-[0.125px] text-[#31302e] ml-1">
            Society Operations Workspace • Pune
          </span>
        </div>

        <div className="flex items-center justify-center gap-3 mb-2">
          <div className="inline-flex items-center justify-center w-10 h-10 rounded-[8px] bg-[#000000] text-white border border-[#e6e6e6]">
            <Building2 className="w-5 h-5" />
          </div>
          <h1 className="text-[26px] sm:text-[32px] font-bold tracking-[-0.625px] text-[#000000] leading-tight">
            Marvel Greenfield Residences
          </h1>
        </div>

        <p className="text-[15px] text-[#615d59] max-w-md mx-auto leading-[1.33]">
          Warm, paper-calm residential governance, billing, gate security &amp; facility workspace.
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-lg px-4 sm:px-0">
        {/* Notion ex-auth-form-card (rounded.xl = 16px, 1px hairline #e6e6e6, Level-1 whisper shadow) */}
        <div className="bg-[#ffffff] py-6 px-6 sm:px-7 border border-[#e6e6e6] shadow-sm rounded-[16px]">
          {children}
        </div>

        <div className="mt-5 flex items-center justify-center gap-2 text-[14px] text-[#a39e98]">
          <ShieldCheck className="h-4 w-4 text-[#1aae39]" />
          <span>Multi-tenant Isolation • Supabase Auth • End-to-End Auditing</span>
        </div>
      </div>
    </div>
  );
};
