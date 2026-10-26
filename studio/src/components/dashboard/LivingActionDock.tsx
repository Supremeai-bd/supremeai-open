import React from 'react';

export interface LivingActionDockProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const LivingActionDock: React.FC<LivingActionDockProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`livingactiondock-stub ${className}`} data-testid="livingactiondock-stub" {...props}>
      {children}
    </div>
  );
};

export default LivingActionDock;
