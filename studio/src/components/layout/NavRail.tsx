import React from 'react';

export interface NavRailProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const NavRail: React.FC<NavRailProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`navrail-stub ${className}`} data-testid="navrail-stub" {...props}>
      {children}
    </div>
  );
};

export default NavRail;
