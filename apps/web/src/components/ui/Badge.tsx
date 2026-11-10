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
  const variants = {
    neutral: 'bg-[#f6f5f4] text-[#31302e] border-[#e6e6e6]',
    success: 'bg-white text-[#1aae39] border-[#e6e6e6]',
    warning: 'bg-white text-[#dd5b00] border-[#e6e6e6]',
    info: 'bg-white text-[#0075de] border-[#e6e6e6]',
    danger: 'bg-white text-[#793400] border-[#e6e6e6]',
  };

  return (
    <span
      className={twMerge(
        clsx(
          'inline-flex items-center px-2 py-1 rounded-full text-[12px] font-semibold tracking-[0.125px] leading-[1.33] border',
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
