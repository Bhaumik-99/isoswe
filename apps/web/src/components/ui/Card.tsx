import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export type CardProps = React.HTMLAttributes<HTMLDivElement>;

export const Card: React.FC<CardProps> = ({ className, children, ...props }) => {
  return (
    <div
      className={twMerge(
        clsx('bg-white border border-[#e6e6e6] rounded-[12px] text-[#000000]', className)
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
    <div className={twMerge(clsx('px-6 py-4 border-b border-[#e6e6e6]', className))} {...props}>
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
        clsx('text-[18px] font-bold tracking-[-0.25px] text-[#000000]', className)
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
