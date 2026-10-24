import React from 'react';
import { cn } from '../../utils/cn';

// বাংলা মন্তব্য: Card কম্পোনেন্টে title ও icon props গ্রহণ ও রেন্ডার করার সাপোর্ট যোগ করা হলো
export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode;
  icon?: React.ReactNode;
  banglaHint?: string;
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, title, icon, banglaHint, children, ...props }, ref) => (
    <div
      ref={ref}
      title={banglaHint}
      className={cn(
        "rounded-xl border border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] bg-[var(--supremeai-color-bg-elevated-light)] dark:bg-[var(--supremeai-color-bg-elevated-dark)] text-foreground shadow-sm",
        className
      )}
      {...props}
    >
      {(title || icon) && (
        <CardHeader className="flex flex-row items-center gap-2 border-b border-[var(--supremeai-color-border-accent-light)] dark:border-[var(--supremeai-color-border-accent-dark)] pb-3 mb-4">
          {icon && <span className="text-xl">{icon}</span>}
          {title && (typeof title === 'string' ? <CardTitle>{title}</CardTitle> : title)}
        </CardHeader>
      )}
      {children}
    </div>
  )
)
Card.displayName = "Card"

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("flex flex-col space-y-1.5 p-6", className)}
      {...props}
    />
  )
)
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn(
        "text-2xl font-semibold leading-none tracking-tight",
        className
      )}
      {...props}
    />
  )
)
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
)
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  )
)
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("flex items-center p-6 pt-0", className)}
      {...props}
    />
  )
)
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter }
