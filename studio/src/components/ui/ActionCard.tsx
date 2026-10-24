import { Card } from './Card';

interface ActionCardProps {
  icon: React.ReactNode;
  title: string;
  description?: string;
  onClick?: () => void;
  variant?: 'default' | 'loading' | 'error' | 'success';
}

export function ActionCard({
  icon,
  title,
  description,
  onClick,
  variant = 'default',
}: ActionCardProps) {
  const handleClick = () => {
    if (onClick) {
      onClick();
    }
  };

  const borderClass = variant === 'error'
    ? 'border-[#ff4d4f]'
    : variant === 'success'
    ? 'border-[#10b981]'
    : '';

  return (
    <div onClick={handleClick} className={`cursor-pointer ${variant === 'loading' ? 'animate-pulse' : ''}`}>
      <Card className={`hover:shadow-lg transition-shadow ${borderClass}`}>
        <div className="flex flex-col items-start gap-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--neon-blue)]/10 text-[var(--neon-blue)]">
              {icon}
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-[var(--foreground)]">{title}</h3>
              {description && (
                <p className="text-[var(--foreground)]/70 text-sm">{description}</p>
              )}
            </div>
          </div>
          {variant === 'loading' && (
            <div className="w-full h-2 bg-[var(--neon-blue)]/20 rounded-full overflow-hidden">
              <div className="h-full w-[30%] bg-[var(--neon-blue)] animate-[progress_8s_linear_infinite]"></div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
