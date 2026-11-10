import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { AlertCircle, AlertTriangle, CheckCircle, Info } from 'lucide-react';

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'info' | 'warning' | 'error' | 'success';
  title?: string;
}

export const Alert: React.FC<AlertProps> = ({
  className,
  variant = 'info',
  title,
  children,
  ...props
}) => {
  const configs = {
    info: {
      bg: 'bg-blue-50/70 border-blue-200 text-slate-800',
      titleColor: 'text-blue-900',
      icon: <Info className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
    warning: {
      bg: 'bg-amber-50/80 border-amber-200 text-amber-950',
      titleColor: 'text-amber-900',
      icon: <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
    error: {
      bg: 'bg-red-50/80 border-red-200 text-red-950',
      titleColor: 'text-red-900',
      icon: <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
    success: {
      bg: 'bg-emerald-50/80 border-emerald-200 text-emerald-950',
      titleColor: 'text-emerald-900',
      icon: <CheckCircle className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
  };

  const { bg, titleColor, icon } = configs[variant];

  return (
    <div
      role="alert"
      className={twMerge(clsx('flex gap-3 p-4 rounded-xl border text-sm shadow-xs', bg, className))}
      {...props}
    >
      {icon}
      <div className="flex-1 min-w-0">
        {title && <h5 className={clsx('font-semibold mb-1 leading-tight', titleColor)}>{title}</h5>}
        <div className="leading-relaxed text-slate-700">{children}</div>
      </div>
    </div>
  );
};
