import React from 'react';

export interface SidebarProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const Sidebar: React.FC<SidebarProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`sidebar-stub ${className}`} data-testid="sidebar-stub" {...props}>
      {children}
    </div>
  );
};

export default Sidebar;
