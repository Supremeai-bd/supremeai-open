import React from 'react';

export interface HomeFeedProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const HomeFeed: React.FC<HomeFeedProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`homefeed-stub ${className}`} data-testid="homefeed-stub" {...props}>
      {children}
    </div>
  );
};

export default HomeFeed;
