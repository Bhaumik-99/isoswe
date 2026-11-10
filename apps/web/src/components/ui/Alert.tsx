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
      bg: 'bg-white border-[#e6e6e6] text-[#000000]',
      icon: <Info className="h-5 w-5 text-[#0075de] flex-shrink-0" />,
    },
    warning: {
      bg: 'bg-[#f6f5f4] border-[#e6e6e6] text-[#31302e]',
      icon: <AlertTriangle className="h-5 w-5 text-[#dd5b00] flex-shrink-0" />,
    },
    error: {
      bg: 'bg-white border-[#dd5b00]/40 text-[#793400]',
      icon: <AlertCircle className="h-5 w-5 text-[#dd5b00] flex-shrink-0" />,
    },
    success: {
      bg: 'bg-white border-[#e6e6e6] text-[#000000]',
      icon: <CheckCircle className="h-5 w-5 text-[#1aae39] flex-shrink-0" />,
    },
  };

  const { bg, icon } = configs[variant];

  return (
    <div
      role="alert"
      className={twMerge(clsx('flex gap-3 p-4 rounded-[12px] border text-[15px] shadow-sm', bg, className))}
      {...props}
    >
      {icon}
      <div className="flex-1">
        {title && <h5 className="font-semibold mb-1 leading-tight text-[#000000]">{title}</h5>}
        <div className="leading-relaxed text-[#31302e]">{children}</div>
      </div>
    </div>
  );
};
