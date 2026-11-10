import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export type CardProps = React.HTMLAttributes<HTMLDivElement>;

// Apple store-utility-card: pure white #ffffff, 1px #e0e0e0 hairline border, rounded 18px, ZERO box shadow
export const Card: React.FC<CardProps> = ({ className, children, ...props }) => {
  return (
    <div
      className={twMerge(
        clsx('bg-[#ffffff] border border-[#e0e0e0] rounded-[18px] text-[#1d1d1f]', className)
      )}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  className,
  children,
  ...props
}) => {
  return (
    <div className={twMerge(clsx('px-6 py-4 border-b border-[#e0e0e0]', className))} {...props}>
      {children}
    </div>
  );
};

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  className,
  children,
  ...props
}) => {
  return (
    <h3
      className={twMerge(
        clsx('font-display text-[21px] font-semibold leading-[1.19] tracking-[0.231px] text-[#1d1d1f]', className)
      )}
      {...props}
    >
      {children}
    </h3>
  );
};

export const CardContent: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  className,
  children,
  ...props
}) => {
  return (
    <div className={twMerge(clsx('p-6', className))} {...props}>
      {children}
    </div>
  );
};
