/**
 * Federation Cockpit — Swarm defense gauge.
 *
 * Visualizes atomic-claim pressure against the configured rate-limit
 * ceiling plus Swarm DoS rejection telemetry.
 */

import type { SwarmDefenseState } from '../types/federation';

export interface SwarmDefenseGaugeProps {
  defense: SwarmDefenseState;
}

export function SwarmDefenseGauge({ defense }: SwarmDefenseGaugeProps) {
  const capacity = Math.max(1, defense.rateLimitCapacity);
  const utilization = Math.min(1, defense.activeClaims / capacity);
  const utilizationPct = Math.round(utilization * 100);
  const level = utilization >= 0.9 ? 'critical' : utilization >= 0.6 ? 'elevated' : 'nominal';

  return (
    <section className={`cockpit-panel defense-panel defense-${level}`} aria-label="Swarm defense gauge">
      <h2 className="cockpit-panel-title">Swarm Defense</h2>
      <div
        className="defense-gauge"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={defense.rateLimitCapacity}
        aria-valuenow={defense.activeClaims}
        aria-label={`Claim capacity utilization ${utilizationPct} percent`}
      >
        <div className="defense-gauge-fill" style={{ width: `${utilizationPct}%` }} />
        <span className="defense-gauge-label">
          {defense.activeClaims}/{defense.rateLimitCapacity} claims
        </span>
      </div>
      <dl className="defense-stats">
        <div className="defense-stat">
          <dt>Rejections</dt>
          <dd data-testid="defense-rejections">{defense.claimRejections}</dd>
        </div>
        <div className="defense-stat">
          <dt>Task velocity</dt>
          <dd>{defense.taskVelocityPerHour}/h</dd>
        </div>
        <div className="defense-stat">
          <dt>Pressure</dt>
          <dd className={`defense-level defense-level-${level}`}>{level}</dd>
        </div>
      </dl>
    </section>
  );
}

export default SwarmDefenseGauge;
