import React from 'react';
import { Skeleton as CommonSkeleton, WorkspaceSkeleton } from '../common/Skeleton';

export interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
}

export const Skeleton: React.FC<SkeletonProps> = (props) => {
  return <CommonSkeleton {...props} />;
};

export { WorkspaceSkeleton };
