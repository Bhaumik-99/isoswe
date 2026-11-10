import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'neutral' | 'success' | 'warning' | 'info' | 'danger';
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = 'neutral',
  children,
  ...props
}) => {
  // Single Action Blue (#0066cc) + crisp Apple neutral monochrome states
  const variants = {
    neutral: 'bg-[#f5f5f7] text-[#333333] border-[#e0e0e0]',
    success: 'bg-[#ffffff] text-[#1d1d1f] border-[#e0e0e0]',
    warning: 'bg-[#fafafc] text-[#333333] border-[#d2d2d7]',
    info: 'bg-[#ffffff] text-[#0066cc] border-[#0066cc]',
    danger: 'bg-[#1d1d1f] text-[#ffffff] border-[#1d1d1f]',
  };

  return (
    <span
      className={twMerge(
        clsx(
          'inline-flex items-center px-3 py-1 rounded-full text-[12px] font-semibold tracking-[-0.12px] leading-none border whitespace-nowrap',
          variants[variant],
          className
        )
      )}
      {...props}
    >
      {children}
    </span>
  );
};
