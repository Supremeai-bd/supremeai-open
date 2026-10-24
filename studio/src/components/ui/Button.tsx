import React from 'react';
import { cn } from '../../utils/cn';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  state?: 'default' | 'loading';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', state = 'default', children, disabled, ...props }, ref) => {

    // Style Dictionary semantic tokens map directly to CSS variables or Tailwind utility classes
    // Assuming variables like --supremeai-semantic-color-action-primary-bg are generated

    const baseStyles = "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50";

    const variants = {
      primary: "bg-[var(--supremeai-semantic-color-action-primary-bg)] text-[var(--supremeai-semantic-color-action-primary-text)] hover:opacity-90 shadow-md",
      secondary: "bg-transparent border border-[var(--supremeai-color-neutral-200)] text-foreground hover:bg-[var(--supremeai-color-neutral-50)]",
      ghost: "bg-transparent hover:bg-[var(--supremeai-color-neutral-50)] text-foreground",
      danger: "bg-[var(--supremeai-color-brand-danger-light)] text-white hover:opacity-90"
    };

    const sizes = {
      sm: "h-8 px-3 text-sm",
      md: "h-10 px-4 py-2",
      lg: "h-12 px-8 text-lg"
    };

    return (
      <button
        ref={ref}
        disabled={disabled || state === 'loading'}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        {...props}
      >
        {state === 'loading' ? (
          <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        ) : null}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
