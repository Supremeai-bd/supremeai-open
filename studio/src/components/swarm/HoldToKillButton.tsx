import React, { useState, useRef } from 'react';

interface Props {
  /** Fired once after the hold completes (2s fill). */
  onTrigger: () => void;
  /** Idle label — e.g. 'Cancel'. */
  label?: string;
  /** Label shown while holding. */
  holdingLabel?: string;
  /** testid for tests/e2e. */
  testId?: string;
  disabled?: boolean;
}

// বাংলা মন্তব্য: Task-12 ghost activation — এই hold-to-confirm বাটনটি আগে কোথাও
// ব্যবহৃত হতো না (dead component)। এখন RunsPage-এর cancel (irreversible,
// state-machine-validated POST /api/v1/runs/{run_id}/cancel) অ্যাকশনের সাথে wire
// করা হয়েছে: 2 সেকেন্ড চেপে ধরলেই কেবল কাজ হবে — দুর্ঘটনাজনিত cancel আটকায়।
// Keyboard ব্যবহারকারীদের জন্য Space/Enter hold-ও একই আচরণ দেয় (a11y parity)।
export const HoldToKillButton: React.FC<Props> = ({
  onTrigger,
  label = 'HOLD TO HALT SWARM',
  holdingLabel = 'HOLDING TO KILL...',
  testId,
  disabled = false,
}) => {
  const [isHolding, setIsHolding] = useState(false);
  const triggerRef = useRef(false); // To prevent double triggers

  const startHold = () => {
    if (disabled) return;
    setIsHolding(true);
    triggerRef.current = false;
  };

  const endHold = () => {
    setIsHolding(false);
  };

  const handleTransitionEnd = () => {
    if (isHolding && !triggerRef.current) {
      triggerRef.current = true;
      onTrigger();
      setIsHolding(false); // Reset visual state
    }
  };

  return (
    <button
      type="button"
      data-testid={testId}
      aria-disabled={disabled || undefined}
      disabled={disabled}
      aria-label={`${label} (hold 2 seconds to confirm)`}
      className="relative inline-block cursor-pointer select-none overflow-hidden rounded-[var(--sa-radius-sm)] border border-[var(--sa-border)] p-0 font-medium text-[var(--sa-ink-muted)] transition-colors hover:border-red-400 hover:text-red-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-400 disabled:cursor-not-allowed disabled:opacity-50"
      onPointerDown={startHold}
      onPointerUp={endHold}
      onPointerLeave={endHold}
      onKeyDown={(e) => {
        if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) startHold();
      }}
      onKeyUp={endHold}
      onBlur={endHold}
    >
      {/* Background/Progress Layer (Fills up in 2 seconds) */}
      <div
        data-testid={testId ? `${testId}-fill` : undefined}
        className="absolute left-0 top-0 h-full bg-red-500/40"
        style={{
          width: isHolding ? '100%' : '0%',
          transition: isHolding ? 'width 2s linear' : 'width 0.3s ease-out',
        }}
        onTransitionEnd={handleTransitionEnd}
      />

      {/* Button Text & Styling */}
      <span className="relative z-10 inline-flex items-center px-3 py-1.5 text-xs">
        {isHolding ? holdingLabel : label}
      </span>
    </button>
  );
};
