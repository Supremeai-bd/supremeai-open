import React from 'react';

export interface ShellProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const Shell: React.FC<ShellProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`shell-stub ${className}`} data-testid="shell-stub" {...props}>
      {children}
    </div>
  );
};

export default Shell;
