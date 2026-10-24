import { useMemo, useState } from 'react';
import { ArrowRight, Check, Link2, Loader2, Plus, Search, Sparkles, X } from 'lucide-react';
import { ADD_INTENTS, type AddIntent, type UserCapability } from '../../types/contracts';
import { connectionsApi } from '../../services/connectionsApi';
import type { ConnectionDetection } from '../../types/contracts';

interface AddNewWizardProps {
  capabilities: UserCapability[];
  onClose: () => void;
  onAdd: (capability: UserCapability) => void;
  onRegistered?: () => void;
}

export function AddNewWizard({ capabilities, onClose, onAdd, onRegistered }: AddNewWizardProps) {
  const [intent, setIntent] = useState<AddIntent>('service');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<UserCapability | null>(null);

  // URL paste & auto-detection state (Acid Test 10 / Universal Intent)
  const [urlInput, setUrlInput] = useState('');
  const [toolName, setToolName] = useState('');
  const [detecting, setDetecting] = useState(false);
  const [detection, setDetection] = useState<ConnectionDetection | null>(null);
  const [registering, setRegistering] = useState(false);
  const [registerSuccess, setRegisterSuccess] = useState<string | null>(null);
  const [registerError, setRegisterError] = useState<string | null>(null);

  const matches = useMemo(
    () =>
      capabilities.filter((item) =>
        `${item.label} ${item.description}`.toLowerCase().includes(query.toLowerCase())
      ),
    [capabilities, query]
  );

  const handleUrlBlurOrChange = async (val: string) => {
    setUrlInput(val);
    const trimmed = val.trim();
    if (trimmed.length > 5 && (trimmed.startsWith('http') || trimmed.startsWith('mcp'))) {
      setDetecting(true);
      setRegisterError(null);
      try {
        const res = await connectionsApi.detectConnection(trimmed);
        setDetection(res);
        if (!toolName) {
          setToolName(res.providerLabel || 'Custom Tool');
        }
      } catch (err: unknown) {
        console.warn('Protocol detection error:', err);
      } finally {
        setDetecting(false);
      }
    } else {
      setDetection(null);
    }
  };

  const handleRegisterUrl = async () => {
    if (!urlInput.trim()) return;
    setRegistering(true);
    setRegisterError(null);
    try {
      const res = await connectionsApi.registerConnection({
        name: toolName.trim() || detection?.providerLabel || 'Custom Tool',
        url: urlInput.trim(),
      });
      setRegisterSuccess(res.message || 'Connection registered successfully.');
      setTimeout(() => {
        if (onRegistered) onRegistered();
        onClose();
      }, 1200);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Registration failed';
      setRegisterError(message);
    } finally {
      setRegistering(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-capability-title"
    >
      <div className="w-full max-w-2xl rounded-2xl border border-[var(--sa-border)] bg-[var(--sa-surface)] p-6 text-[var(--sa-ink)] shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="sa-eyebrow">Workspace control plane</p>
            <h2 id="add-capability-title" className="mt-2 text-xl font-semibold">
              Add something useful
            </h2>
            <p className="mt-1 font-sans text-sm text-[var(--sa-ink-muted)]">
              Paste a URL to connect directly, or choose from available workspace capabilities.
            </p>
          </div>
          <button
            className="rounded-lg p-2 hover:bg-[var(--sa-surface-raised)]"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Universal URL input (One-Input / Acid Test 10) */}
        <div className="mt-5 rounded-xl border border-[var(--sa-border)] bg-[var(--sa-surface-raised)] p-4">
          <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--sa-ink-muted)] mb-2 flex items-center gap-1.5">
            <Link2 size={14} /> Paste URL or Service Endpoint
          </label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={urlInput}
              onChange={(e) => handleUrlBlurOrChange(e.target.value)}
              placeholder="e.g. https://github.com, mcp://my-server, or any web service..."
              className="w-full bg-[var(--sa-canvas)] px-3 py-2.5 rounded-lg border border-[var(--sa-border)] font-sans text-sm outline-none focus:border-[var(--sa-primary)]"
            />
            {detecting && <Loader2 size={18} className="animate-spin text-[var(--sa-primary)]" />}
          </div>

          {detection && (
            <div className="mt-3 flex items-center justify-between rounded-lg bg-[var(--sa-primary-soft)] px-3 py-2 text-xs">
              <span className="flex items-center gap-2 font-medium text-[var(--sa-primary)]">
                <Sparkles size={14} /> Detected: {detection.providerLabel} ({detection.protocol.toUpperCase()})
              </span>
              <button
                type="button"
                disabled={registering}
                onClick={handleRegisterUrl}
                className="inline-flex items-center gap-1.5 rounded-md bg-[var(--sa-primary)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-50"
              >
                {registering ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                Connect
              </button>
            </div>
          )}

          {registerSuccess && (
            <p className="mt-2 text-xs font-medium text-emerald-500 flex items-center gap-1">
              <Check size={14} /> {registerSuccess}
            </p>
          )}
          {registerError && (
            <p className="mt-2 text-xs font-medium text-rose-500">
              {registerError}
            </p>
          )}
        </div>

        <div className="relative my-5 text-center">
          <hr className="border-[var(--sa-border)]" />
          <span className="absolute left-1/2 -top-2.5 -translate-x-1/2 bg-[var(--sa-surface)] px-3 text-xs text-[var(--sa-ink-muted)]">
            or choose an outcome
          </span>
        </div>

        {/* Intent Pills */}
        <div className="grid gap-2 sm:grid-cols-2">
          {ADD_INTENTS.map((item) => (
            <button
              key={item.id}
              onClick={() => setIntent(item.id)}
              className={`rounded-xl border p-3 text-left transition ${
                intent === item.id
                  ? 'border-[var(--sa-primary)] bg-[var(--sa-primary)]/10'
                  : 'border-[var(--sa-border)] hover:bg-[var(--sa-surface-raised)]'
              }`}
            >
              <span className="text-sm font-medium">{item.label}</span>
              <span className="mt-1 block font-sans text-xs text-[var(--sa-ink-muted)]">
                {item.description}
              </span>
            </button>
          ))}
        </div>

        {/* Search capabilities */}
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-[var(--sa-border)] bg-[var(--sa-surface-raised)] px-3">
          <Search size={16} className="text-[var(--sa-ink-muted)]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Search ${intent} capabilities`}
            className="w-full bg-transparent py-2.5 font-sans text-sm outline-none"
          />
        </div>

        {/* Matches */}
        <div className="mt-3 grid max-h-48 gap-2 overflow-y-auto">
          {matches.map((item) => (
            <button
              key={item.id}
              onClick={() => setSelected(item)}
              className={`flex items-center justify-between rounded-xl border p-3 text-left ${
                selected?.id === item.id
                  ? 'border-[var(--sa-primary)] bg-[var(--sa-primary)]/5'
                  : 'border-[var(--sa-border)] hover:bg-[var(--sa-surface-raised)]'
              }`}
            >
              <span>
                <span className="block text-sm font-medium">{item.label}</span>
                <span className="font-sans text-xs text-[var(--sa-ink-muted)]">
                  {item.description}
                </span>
              </span>
              {selected?.id === item.id ? (
                <Check size={17} className="text-[var(--sa-primary)]" />
              ) : (
                <ArrowRight size={17} className="text-[var(--sa-ink-muted)]" />
              )}
            </button>
          ))}
          {matches.length === 0 && (
            <p className="rounded-xl border border-dashed border-[var(--sa-border)] p-4 text-center font-sans text-sm text-[var(--sa-ink-muted)]">
              No available capability matches this request.
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 font-sans text-sm text-[var(--sa-ink-muted)] hover:bg-[var(--sa-surface-raised)]"
          >
            Cancel
          </button>
          <button
            disabled={!selected}
            onClick={() => selected && onAdd(selected)}
            className="flex items-center gap-2 rounded-lg bg-[var(--sa-primary)] px-4 py-2 font-sans text-sm text-[var(--sa-primary-foreground)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Plus size={16} />
            Add capability
          </button>
        </div>
      </div>
    </div>
  );
}

export default AddNewWizard;
