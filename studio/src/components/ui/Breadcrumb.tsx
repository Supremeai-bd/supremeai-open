import React from 'react';
import { cn } from '../../utils/cn';

export interface Crumb {
  label: string;
  href?: string;
}

export interface BreadcrumbProps {
  items: Crumb[];
  className?: string;
}

// বাংলা মন্তব্য: Breadcrumb — ডিপ ট্রি নেভিগেশনে orientation; শেষ আইটেম active।
export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav
      aria-label="Breadcrumb"
      className={cn('flex items-center gap-1.5 text-sm text-slate-400', className)}
    >
      {items.map((crumb, i) => {
        const isLast = i === items.length - 1;
        return (
          <React.Fragment key={`${crumb.label}-${i}`}>
            <li className="inline-flex items-center gap-1.5">
              {i > 0 && <span className="text-slate-600 select-none">›</span>}
              {isLast ? (
                <span
                  aria-current="page"
                  className="font-medium text-foreground text-slate-100"
                >
                  {crumb.label}
                </span>
              ) : (
                <a href={crumb.href} className="hover:text-cyan-400">
                  {crumb.label}
                </a>
              )}
            </li>
          </React.Fragment>
        );
      })}
    </nav>
  );
}

export default Breadcrumb;
