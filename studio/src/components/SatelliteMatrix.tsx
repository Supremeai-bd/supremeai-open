/**
 * Federation Cockpit — 11+1 Satellite health & parity matrix.
 *
 * Real-time grid of every canonical federation satellite: health dot,
 * latest commit SHA, last Nightly Train sync, and active claim counts.
 */

import type { SatelliteHealth } from '../types/federation';

export interface SatelliteMatrixProps {
  satellites: SatelliteHealth[];
}

function shortSha(sha?: string): string {
  return sha ? sha.slice(0, 7) : '—';
}

function relativeTime(iso?: string): string {
  if (!iso) {
    return 'never';
  }
  const then = Date.parse(iso);
  if (Number.isNaN(then)) {
    return 'unknown';
  }
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function SatelliteMatrix({ satellites }: SatelliteMatrixProps) {
  const healthyCount = satellites.filter((s) => s.healthy).length;
  return (
    <section className="cockpit-panel" aria-label="Satellite health matrix">
      <h2 className="cockpit-panel-title">
        Satellite Matrix{' '}
        <span className="satellite-parity" data-healthy={healthyCount} data-total={satellites.length}>
          {healthyCount}/{satellites.length} healthy
        </span>
      </h2>
      <div className="satellite-grid" role="grid">
        {satellites.map((satellite) => (
          <div
            className={`satellite-cell ${satellite.healthy ? 'satellite-up' : 'satellite-down'}`}
            role="gridcell"
            key={satellite.id}
            aria-label={`${satellite.displayName}: ${satellite.healthy ? 'healthy' : 'unhealthy'}`}
          >
            <div className="satellite-cell-head">
              <span className={`ci-dot ${satellite.healthy ? 'ci-dot-green' : 'ci-dot-red'}`} aria-hidden="true" />
              <span className="satellite-name">{satellite.displayName}</span>
              {typeof satellite.activeClaims === 'number' && satellite.activeClaims > 0 ? (
                <span className="satellite-claims">{satellite.activeClaims} claim</span>
              ) : null}
            </div>
            <div className="satellite-cell-meta">
              <span className="satellite-sha">{shortSha(satellite.latestSha)}</span>
              <span className="satellite-sync">{relativeTime(satellite.lastSyncedAt)}</span>
              {typeof satellite.latencyMs === 'number' ? (
                <span className="satellite-latency">{satellite.latencyMs}ms</span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default SatelliteMatrix;
