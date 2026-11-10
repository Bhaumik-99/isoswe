import React from 'react';
import { Link } from 'react-router-dom';
import { FileQuestion, ArrowLeft } from 'lucide-react';
import { Button } from './ui/Button';

export const NotFound: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#f5f5f7] flex items-center justify-center p-4">
      <div className="max-w-md w-full text-center bg-[#ffffff] p-10 rounded-[18px] border border-[#e0e0e0]">
        <div className="w-14 h-14 bg-[#f5f5f7] text-[#1d1d1f] border border-[#e0e0e0] rounded-full flex items-center justify-center mx-auto mb-5">
          <FileQuestion className="w-6 h-6" aria-hidden="true" />
        </div>
        <h1 className="font-display text-[34px] font-semibold leading-[1.2] tracking-[-0.374px] text-[#1d1d1f] mb-2">
          Page Not Found
        </h1>
        <p className="text-[17px] text-[#333333] leading-[1.47] tracking-[-0.374px] mb-8">
          The requested path does not exist in this township operations deployment.
        </p>
        <Link to="/" className="inline-block">
          <Button variant="primary" size="lg">
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            <span>Return to Dashboard</span>
          </Button>
        </Link>
      </div>
    </div>
  );
};
