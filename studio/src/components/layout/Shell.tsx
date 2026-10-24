import React from 'react';
import { cn } from '../../utils/cn';

interface ShellProps extends React.HTMLAttributes<HTMLDivElement> {
  sidebar?: React.ReactNode;
  header?: React.ReactNode;
}

export const Shell = React.forwardRef<HTMLDivElement, ShellProps>(
  ({ className, sidebar, header, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn("flex h-screen w-full bg-[var(--supremeai-color-bg-void-light)] dark:bg-[var(--supremeai-color-bg-void-dark)] overflow-hidden text-foreground", className)}
        {...props}
      >
        {/* Sidebar */}
        {sidebar && (
          <aside className="w-64 border-r border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] bg-[var(--supremeai-color-bg-elevated-light)] dark:bg-[var(--supremeai-color-bg-elevated-dark)] flex flex-col transition-colors z-20">
            {sidebar}
          </aside>
        )}

        {/* Main Content Area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Header */}
          {header && (
            <header className="h-14 border-b border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] bg-[var(--supremeai-color-bg-elevated-light)] dark:bg-[var(--supremeai-color-bg-elevated-dark)] flex items-center px-6 transition-colors z-10 shadow-sm">
              {header}
            </header>
          )}

          {/* Scrollable Content */}
          <main className="flex-1 overflow-auto p-6 relative">
            {children}
          </main>
        </div>
      </div>
    );
  }
);

Shell.displayName = 'Shell';
