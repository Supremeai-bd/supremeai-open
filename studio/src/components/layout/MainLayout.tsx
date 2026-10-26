import React from 'react';

export interface MainLayoutProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const MainLayout: React.FC<MainLayoutProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`mainlayout-stub ${className}`} data-testid="mainlayout-stub" {...props}>
      {children}
    </div>
  );
};

export default MainLayout;
