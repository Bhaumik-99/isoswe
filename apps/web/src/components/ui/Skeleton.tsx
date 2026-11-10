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
      className={twMerge(clsx('animate-pulse rounded-xl bg-slate-200/75', className))}
      {...props}
    />
  );
};
