// apps/studio-client/src/components/common/Skeleton.tsx
// Modern Animated UI Skeleton Component
// বাংলা মন্তব্য: আধুনিক অ্যানিমেটেড কঙ্কাল (Skeleton) লোডার কম্পোনেন্ট — মসৃণ লোডিং স্টেটের জন্য।

import React from 'react';

interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className = '',
  variant = 'rectangular',
  width,
  height,
}) => {
  const getVariantStyle = () => {
    switch (variant) {
      case 'circular':
        return 'rounded-full';
      case 'text':
        return 'rounded h-4 my-1';
      default:
        return 'rounded-xl';
    }
  };

  return (
    <div
      style={{ width, height }}
      className={`animate-pulse bg-slate-800/60 border border-slate-700/40 ${getVariantStyle()} ${className}`}
    />
  );
};

export const WorkspaceSkeleton: React.FC = () => {
  return (
    <div className="flex flex-col h-full w-full p-6 gap-6 bg-slate-950 text-slate-400">
      <div className="flex items-center justify-between">
        <Skeleton width={200} height={32} />
        <div className="flex gap-2">
          <Skeleton width={80} height={36} />
          <Skeleton width={120} height={36} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1">
        <div className="md:col-span-2 flex flex-col gap-4">
          <Skeleton height={240} className="w-full" />
          <Skeleton height={180} className="w-full" />
        </div>
        <div className="flex flex-col gap-4">
          <Skeleton height={120} className="w-full" />
          <Skeleton height={300} className="w-full" />
        </div>
      </div>
    </div>
  );
};

export default Skeleton;
