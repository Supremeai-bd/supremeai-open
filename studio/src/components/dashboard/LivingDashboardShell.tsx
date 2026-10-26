import React from 'react';

export interface LivingDashboardShellProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const LivingDashboardShell: React.FC<LivingDashboardShellProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`livingdashboardshell-stub ${className}`} data-testid="livingdashboardshell-stub" {...props}>
      {children}
    </div>
  );
};

export default LivingDashboardShell;
