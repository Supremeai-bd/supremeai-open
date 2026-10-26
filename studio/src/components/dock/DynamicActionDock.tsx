import React from 'react';

export interface DynamicActionDockProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const DynamicActionDock: React.FC<DynamicActionDockProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`dynamicactiondock-stub ${className}`} data-testid="dynamicactiondock-stub" {...props}>
      {children}
    </div>
  );
};

export default DynamicActionDock;
