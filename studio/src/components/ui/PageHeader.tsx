import React from 'react';
import { cn } from '../../utils/cn';
import { Breadcrumb, type Crumb } from './Breadcrumb';

export interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  crumbItems?: Crumb[];
  actions?: React.ReactNode;
  className?: string;
}

// বাংলা মন্তব্য: Page hero — eyebrow + H1 + subtitle (রেফারেন্স "ADMIN DASHBOARD / Welcome back, Alex" প্যাটার্ন)।
export function PageHeader({ eyebrow, title, subtitle, crumbItems, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('mb-6 flex flex-col gap-3', className)}>
      {crumbItems && crumbItems.length > 0 && <Breadcrumb items={crumbItems} />}
      {eyebrow && (
        <p className="text-xs font-medium text-[#00f3ff] uppercase tracking-widest">{eyebrow}</p>
      )}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold tracking-tight">{title}</h1>
          {subtitle && <p className="text-sm text-white/80 mt-1 max-w-lg">{subtitle}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export default PageHeader;
