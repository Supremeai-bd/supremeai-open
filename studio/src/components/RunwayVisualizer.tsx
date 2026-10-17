/**
 * Federation Cockpit — Live PR Runway visualizer.
 *
 * Kanban runway for bridge work orders: Queued → In-Gates → Landed /
 * Self-Healing, with CI status dots (green/red/amber) and hover failure
 * diagnostics.
 */

import type { RunwayEntry, RunwayStage } from '../types/federation';

const STAGE_ORDER: readonly RunwayStage[] = ['queued', 'in-gates', 'landed', 'self-healing'];

const STAGE_LABELS: Record<RunwayStage, string> = {
  queued: 'Queued',
  'in-gates': 'In-Gates',
  landed: 'Landed',
  'self-healing': 'Self-Healing',
};

export interface RunwayVisualizerProps {
  entries: RunwayEntry[];
  /** Limits rendered cards per column (default 8). */
  maxPerColumn?: number;
}

export function RunwayVisualizer({ entries, maxPerColumn = 8 }: RunwayVisualizerProps) {
  return (
    <section className="cockpit-panel" aria-label="Live PR runway">
      <h2 className="cockpit-panel-title">Live PR Runway</h2>
      <div className="runway-grid" role="list">
        {STAGE_ORDER.map((stage) => {
          const columnEntries = entries.filter((e) => e.stage === stage).slice(0, maxPerColumn);
          return (
            <div className={`runway-column runway-stage-${stage}`} role="listitem" key={stage}>
              <header className="runway-column-header">
                <span className="runway-column-title">{STAGE_LABELS[stage]}</span>
                <span className="runway-column-count">{columnEntries.length}</span>
              </header>
              <div className="runway-cards">
                {columnEntries.length === 0 ? (
                  <p className="runway-empty">no work orders</p>
                ) : (
                  columnEntries.map((entry) => (
                    <article
                      className={`runway-card ci-${entry.ciStatus}`}
                      key={entry.taskId}
                      title={entry.ciStatus === 'red' ? entry.diagnostics ?? 'CI failed' : entry.title}
                    >
                      <span className={`ci-dot ci-dot-${entry.ciStatus}`} aria-hidden="true" />
                      <div className="runway-card-body">
                        <p className="runway-card-title">{entry.title}</p>
                        <p className="runway-card-meta">
                          {entry.taskId}
                          {entry.prNumber ? ` · PR #${entry.prNumber}` : ''}
                        </p>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default RunwayVisualizer;
