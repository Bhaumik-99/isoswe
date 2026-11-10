import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', isLoading = false, disabled, children, ...props }, ref) => {
    // Apple interaction grammar: active scale(0.95), focus outline #0071e3, no chrome shadows, weight 300/400/600 (never 500)
    const baseStyles =
      'inline-flex items-center justify-center cursor-pointer transition-transform duration-150 focus-visible:outline-2 focus-visible:outline-[#0071e3] focus-visible:outline-offset-2 disabled:text-[#7a7a7a] disabled:opacity-50 disabled:pointer-events-none select-none active:scale-[0.95]';

    const variants = {
      primary:
        'bg-[#0066cc] text-[#ffffff] rounded-full font-normal',
      secondary:
        'bg-[#ffffff] text-[#0066cc] border border-[#0066cc] rounded-full font-normal',
      outline:
        'bg-[#fafafc] text-[#333333] border-[3px] border-[#f0f0f0] rounded-[11px] font-normal',
      ghost:
        'bg-transparent text-[#0066cc] rounded-[5px] font-normal hover:underline',
      danger:
        'bg-[#1d1d1f] text-[#ffffff] rounded-[8px] font-normal',
    };

    const sizes = {
      sm: 'min-h-[36px] px-[15px] py-[8px] text-[14px] leading-[1.29] tracking-[-0.224px] gap-1.5',
      md: 'min-h-[44px] px-[22px] py-[11px] text-[17px] leading-[1.2] tracking-[-0.374px] gap-2',
      lg: 'min-h-[44px] px-[28px] py-[14px] text-[18px] leading-[1.0] font-light tracking-normal gap-2',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={twMerge(clsx(baseStyles, variants[variant], sizes[size], className))}
        {...props}
      >
        {isLoading ? (
          <span className="flex items-center gap-2">
            <svg
              className="animate-spin h-4 w-4 text-current"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <span>Processing...</span>
          </span>
        ) : (
          children
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';
