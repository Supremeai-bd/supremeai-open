import React from 'react';

export interface ActionDockProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const ActionDock: React.FC<ActionDockProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`actiondock-stub ${className}`} data-testid="actiondock-stub" {...props}>
      {children}
    </div>
  );
};

export default ActionDock;
