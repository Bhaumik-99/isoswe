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
      bg: 'bg-[#f5f5f7] border-[#e0e0e0] text-[#1d1d1f]',
      icon: <Info className="h-5 w-5 text-[#0066cc] flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
    warning: {
      bg: 'bg-[#fafafc] border-[#d2d2d7] text-[#1d1d1f]',
      icon: <AlertTriangle className="h-5 w-5 text-[#1d1d1f] flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
    error: {
      bg: 'bg-[#272729] border-[#2a2a2c] text-[#ffffff]',
      icon: <AlertCircle className="h-5 w-5 text-[#2997ff] flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
    success: {
      bg: 'bg-[#ffffff] border-[#e0e0e0] text-[#1d1d1f]',
      icon: <CheckCircle className="h-5 w-5 text-[#0066cc] flex-shrink-0 mt-0.5" aria-hidden="true" />,
    },
  };

  const { bg, icon } = configs[variant];
  const isDark = variant === 'error';

  return (
    <div
      role="alert"
      className={twMerge(clsx('flex gap-3 p-4 rounded-[18px] border text-[14px] leading-[1.43] tracking-[-0.224px]', bg, className))}
      {...props}
    >
      {icon}
      <div className="flex-1 min-w-0">
        {title && (
          <h5 className={clsx('font-semibold mb-1 leading-tight', isDark ? 'text-[#ffffff]' : 'text-[#1d1d1f]')}>
            {title}
          </h5>
        )}
        <div className={clsx('leading-relaxed', isDark ? 'text-[#cccccc]' : 'text-[#333333]')}>{children}</div>
      </div>
    </div>
  );
};
