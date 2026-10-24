import { AlertCircle, CheckCircle2, ExternalLink, Play, Settings2, Trash2 } from 'lucide-react';
import type { UnavailableCapability, UserCapability } from '../../types/contracts';

export interface ManageItemProps {
  item: UserCapability;
  onManage?: () => void;
  onUse?: () => void;
  onRemove?: () => void;
}

/**
 * Universal Manage Model:
 * Use, Configure, Pause, Remove
 */
export function ManageItem({ item, onManage, onUse, onRemove }: ManageItemProps) {
  const isUnavailable = item.status === 'unavailable';

  return (
    <article className="rounded-xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-4 flex flex-col justify-between transition hover:border-[var(--sa-primary)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{item.label}</h3>
          <p className="mt-1 font-sans text-xs leading-5 text-[var(--sa-ink-muted)]">
            {item.description}
          </p>
        </div>
        <span
          className={`flex items-center gap-1 text-[11px] uppercase tracking-wider font-medium ${
            isUnavailable ? 'text-amber-500' : 'text-emerald-500'
          }`}
        >
          {isUnavailable ? (
            <AlertCircle size={13} />
          ) : (
            <CheckCircle2 size={13} />
          )}
          {item.status}
        </span>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-[var(--sa-border)] pt-3">
        <div className="flex items-center gap-2">
          {item.href ? (
            <a
              href={item.href}
              className="inline-flex items-center gap-1 rounded-md bg-[var(--sa-primary-soft)] px-2.5 py-1.5 font-sans text-xs font-medium text-[var(--sa-primary)] hover:opacity-90"
            >
              Open <ExternalLink size={12} />
            </a>
          ) : onUse ? (
            <button
              onClick={onUse}
              className="inline-flex items-center gap-1 rounded-md bg-[var(--sa-primary-soft)] px-2.5 py-1.5 font-sans text-xs font-medium text-[var(--sa-primary)] hover:opacity-90"
            >
              <Play size={12} /> Use
            </button>
          ) : null}
          <button
            onClick={onManage}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--sa-border)] px-2.5 py-1.5 font-sans text-xs text-[var(--sa-ink-muted)] hover:text-[var(--sa-ink)] hover:bg-[var(--sa-surface-raised)]"
          >
            <Settings2 size={12} /> Configure
          </button>
        </div>

        {onRemove && (
          <button
            onClick={onRemove}
            aria-label="Remove capability"
            className="p-1.5 rounded-md text-[var(--sa-ink-muted)] hover:text-rose-500 hover:bg-rose-500/10 transition"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </article>
  );
}

export function CapabilityUnavailableExplainer({
  item,
  onRequest,
}: {
  item: UnavailableCapability;
  onRequest?: () => void;
}) {
  return (
    <article className="rounded-xl border border-dashed border-amber-400/40 bg-amber-400/5 p-4">
      <div className="flex gap-3">
        <AlertCircle className="mt-0.5 text-amber-500 shrink-0" size={18} />
        <div>
          <h3 className="text-sm font-semibold">{item.label} is unavailable</h3>
          <p className="mt-1 font-sans text-xs leading-5 text-[var(--sa-ink-muted)]">
            {item.reason}
          </p>
          {item.requestable && (
            <button
              onClick={onRequest}
              className="mt-3 rounded-lg border border-amber-500/40 px-3 py-1.5 font-sans text-xs font-medium text-amber-600 dark:text-amber-300 hover:bg-amber-400/10"
            >
              Request access
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
