import React from 'react';
import { Link } from 'react-router-dom';
import { FileQuestion, ArrowLeft } from 'lucide-react';
import { Button } from './ui/Button';

export const NotFound: React.FC = () => {
  return (
    <div className="min-h-screen hero-mesh-bg flex items-center justify-center p-4">
      <div className="max-w-md w-full text-center bg-white/95 backdrop-blur-md p-8 rounded-2xl border border-slate-200 shadow-xl">
        <div className="w-14 h-14 bg-blue-50 text-primary-600 border border-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <FileQuestion className="w-7 h-7" aria-hidden="true" />
        </div>
        <h1 className="font-display text-2xl text-slate-900 mb-2">Page Not Found</h1>
        <p className="text-sm text-slate-600 mb-6">
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
