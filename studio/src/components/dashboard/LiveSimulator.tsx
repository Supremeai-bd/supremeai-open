import React from 'react';

export interface LiveSimulatorProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const LiveSimulator: React.FC<LiveSimulatorProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`livesimulator-stub ${className}`} data-testid="livesimulator-stub" {...props}>
      {children}
    </div>
  );
};

export default LiveSimulator;
