/**
 * Studio Cockpit — Multi-Model Consensus widget.
 *
 * Renders the parallel responses returned by /v1/consensus (stealth web relay +
 * groq + gemini) side by side so the operator can compare reasoning. Each
 * column shows provider, status, latency and the extracted assistant content.
 */

export interface ConsensusResponse {
  provider: string;
  slot?: string;
  status: number;
  latency_ms?: number;
  error?: string;
  response?: {
    choices?: Array<{ message?: { content?: string } }>;
  } | null;
}

export interface ConsensusWidgetProps {
  responses: ConsensusResponse[];
  /** Optional overall consensus count reported by the gateway. */
  consensusCount?: number;
  /** Called when the operator wants to re-run the consensus query. */
  onRerun?: () => void;
}

function extractContent(r: ConsensusResponse): string {
  const c = r.response?.choices?.[0]?.message?.content;
  if (typeof c === 'string' && c.trim()) return c;
  if (r.error) return `Error: ${r.error}`;
  return r.status >= 400 ? `HTTP ${r.status}` : '(no content)';
}

export function ConsensusWidget({ responses, consensusCount, onRerun }: ConsensusWidgetProps) {
  return (
    <section className="cockpit-panel consensus-panel" aria-label="Multi-model consensus">
      <header className="cockpit-panel-header">
        <h2 className="cockpit-panel-title">Multi-Model Consensus</h2>
        <div className="consensus-meta">
          <span className="consensus-count">
            {consensusCount ?? responses.filter((r) => r.status >= 200 && r.status < 400).length} / {responses.length} ok
          </span>
          {onRerun ? (
            <button type="button" className="consensus-rerun" onClick={onRerun}>
              Re-run
            </button>
          ) : null}
        </div>
      </header>

      <div className="consensus-grid" role="list">
        {responses.map((r, idx) => {
          const ok = r.status >= 200 && r.status < 400;
          return (
            <article
              key={`${r.provider}-${idx}`}
              className={`consensus-card ${ok ? 'consensus-ok' : 'consensus-fail'}`}
              role="listitem"
            >
              <header className="consensus-card-header">
                <span className="consensus-provider">{r.slot || r.provider}</span>
                <span className={`consensus-status ${ok ? 'status-ok' : 'status-fail'}`}>
                  {ok ? 'OK' : `HTTP ${r.status}`}
                </span>
              </header>
              {r.latency_ms != null ? (
                <p className="consensus-latency">{r.latency_ms} ms</p>
              ) : null}
              <pre className="consensus-content">{extractContent(r)}</pre>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export default ConsensusWidget;
