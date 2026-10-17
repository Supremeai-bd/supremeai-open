/**
 * Federation Cockpit — emergency control console.
 *
 * Autonomy kill-switch with a two-step PIN confirmation modal. The PIN is
 * supplied by the operator via props; the component holds no secrets and
 * performs no network calls itself — it only raises onRequestKill.
 */

import { useState } from 'react';

export interface EmergencyConsoleProps {
  /** Whether the autonomy system is currently armed. */
  armed: boolean;
  /** Called after a valid PIN confirmation. */
  onRequestKill?: (pin: string) => void;
  /** Called when the operator re-arms from the console. */
  onRearm?: () => void;
}

export function EmergencyConsole({ armed, onRequestKill, onRearm }: EmergencyConsoleProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');

  const openConfirm = () => {
    setPin('');
    setError('');
    setConfirmOpen(true);
  };

  const submitPin = () => {
    if (pin.trim().length < 4) {
      setError('PIN must be at least 4 characters');
      return;
    }
    setConfirmOpen(false);
    setPin('');
    onRequestKill?.(pin);
  };

  const closeConfirm = () => {
    setConfirmOpen(false);
    setPin('');
    setError('');
  };

  return (
    <section className="cockpit-panel emergency-panel" aria-label="Emergency console">
      <h2 className="cockpit-panel-title">Emergency Console</h2>
      <p className={`emergency-state ${armed ? 'emergency-armed' : 'emergency-disarmed'}`}>
        {armed ? 'Autonomy: ARMED' : 'Autonomy: KILLED'}
      </p>
      {armed ? (
        <button type="button" className="kill-switch" onClick={openConfirm}>
          Engage Kill-Switch
        </button>
      ) : (
        <button type="button" className="rearm-switch" onClick={onRearm}>
          Re-arm Autonomy
        </button>
      )}

      {confirmOpen ? (
        <div className="kill-modal-backdrop" role="presentation">
          <div className="kill-modal" role="dialog" aria-modal="true" aria-labelledby="kill-modal-title">
            <h3 id="kill-modal-title">Confirm Autonomy Kill-Switch</h3>
            <p>This halts all agent claim activity federation-wide. Enter the operator PIN to confirm.</p>
            <input
              className="kill-pin-input"
              type="password"
              inputMode="numeric"
              autoFocus
              value={pin}
              placeholder="operator PIN"
              aria-label="Operator PIN"
              onChange={(event) => setPin(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  submitPin();
                } else if (event.key === 'Escape') {
                  closeConfirm();
                }
              }}
            />
            {error ? (
              <p className="kill-modal-error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="kill-modal-actions">
              <button type="button" className="kill-cancel" onClick={closeConfirm}>
                Cancel
              </button>
              <button type="button" className="kill-confirm" onClick={submitPin}>
                Confirm Kill
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default EmergencyConsole;
