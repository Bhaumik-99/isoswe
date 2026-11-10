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
    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0075de] focus-visible:ring-offset-1 disabled:opacity-50 disabled:pointer-events-none select-none active:scale-[0.98]';

    const variants = {
      primary:
        'bg-[#0075de] text-white hover:bg-[#005bab] active:bg-[#005bab] rounded-full shadow-sm',
      secondary:
        'bg-white text-[#000000] border border-[#e6e6e6] hover:bg-[#f6f5f4] rounded-full shadow-sm',
      outline:
        'bg-white border border-[#e6e6e6] text-[#000000] hover:bg-[#f6f5f4] rounded-[8px]',
      ghost:
        'text-[#615d59] hover:text-[#000000] hover:bg-[#f6f5f4] rounded-[5px]',
      danger:
        'bg-[#dd5b00] text-white hover:bg-[#793400] rounded-full shadow-sm',
    };

    const sizes = {
      sm: 'h-8 px-3.5 text-xs',
      md: 'h-9 px-4 text-[15px]',
      lg: 'h-11 px-6 text-[16px]',
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
