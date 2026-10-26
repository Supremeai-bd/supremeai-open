import React from 'react';

export interface DashboardLayoutProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`dashboardlayout-stub ${className}`} data-testid="dashboardlayout-stub" {...props}>
      {children}
    </div>
  );
};

export default DashboardLayout;
