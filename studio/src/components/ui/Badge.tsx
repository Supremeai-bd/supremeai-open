import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'purple';
  className?: string;
}

export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  const variants = {
    default: 'bg-slate-950 text-slate-300 border border-slate-800',
    success: 'bg-emerald-950 text-emerald-400 border border-emerald-900',
    warning: 'bg-yellow-950 text-yellow-400 border border-yellow-900',
    danger: 'bg-red-950 text-red-400 border border-red-900',
    info: 'bg-cyan-950 text-[#00f3ff] border border-cyan-900',
    purple: 'bg-purple-950 text-purple-400 border border-purple-900',
  };
  return (
    <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${variants[variant]} ${className}`}>
      {children}
    </span>
  );
}
