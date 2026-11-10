import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export const Skeleton: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  className,
  ...props
}) => {
  return (
    <div
      aria-hidden="true"
      className={twMerge(clsx('animate-pulse rounded-[18px] bg-[#f5f5f7] border border-[#e0e0e0]', className))}
      {...props}
    />
  );
};
