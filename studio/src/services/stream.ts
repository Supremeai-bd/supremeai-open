export interface StreamEvent {
  id: string;
  type: string;
  data: string;
}

export interface StreamOptions {
  url: string;
  token: string;
  onEvent: (event: StreamEvent) => void;
  onStatus?: (status: "connecting" | "connected" | "disconnected") => void;
}

export class EventStream {
  private cursor: string | null = null;
  private seen = new Set<string>();
  private es: EventSource | null = null;
  private attempts = 0;
  private maxAttempts = 10;
  private closed = false;

  constructor(private opts: StreamOptions) {}

  start(): void {
    if (this.closed) return;
    this.opts.onStatus?.("connecting");
    const url = this.cursor
      ? `${this.opts.url}?last-event-id=${encodeURIComponent(this.cursor)}`
      : this.opts.url;
    const es = new EventSource(url, { withCredentials: false });
    this.es = es;

    es.onopen = () => {
      this.attempts = 0;
      this.opts.onStatus?.("connected");
    };

    es.onmessage = (e) => {
      const id = e.lastEventId || String(Date.now());
      if (this.seen.has(id)) return;
      this.seen.add(id);
      this.cursor = id;
      this.opts.onEvent({ id, type: "message", data: e.data });
    };

    es.onerror = () => {
      es.close();
      this.es = null;
      this.opts.onStatus?.("disconnected");
      if (this.closed || this.attempts >= this.maxAttempts) return;
      this.attempts += 1;
      const backoff = Math.min(1000 * 2 ** this.attempts, 30000);
      const jitter = Math.random() * 500;
      setTimeout(() => this.start(), backoff + jitter);
    };
  }

  stop(): void {
    this.closed = true;
    this.es?.close();
    this.es = null;
  }

  resetCursor(): void {
    this.cursor = null;
    this.seen.clear();
  }
}
