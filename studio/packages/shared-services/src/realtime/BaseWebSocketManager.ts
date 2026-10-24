export type WsStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface BaseWebSocketManagerOptions {
  maxReconnectAttempts?: number;
  reconnectBaseDelayMs?: number;
  heartbeatIntervalMs?: number;
}

export abstract class BaseWebSocketManager {
  protected ws: WebSocket | null = null;
  protected status: WsStatus = 'closed';
  protected reconnectAttempts = 0;
  
  protected maxReconnectAttempts: number;
  protected reconnectBaseDelayMs: number;
  protected heartbeatIntervalMs: number;
  
  protected heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  protected reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  protected manuallyClosed = false;

  constructor(options: BaseWebSocketManagerOptions = {}) {
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 5;
    this.reconnectBaseDelayMs = options.reconnectBaseDelayMs ?? 1000;
    this.heartbeatIntervalMs = options.heartbeatIntervalMs ?? 30000;
  }

  // Subclasses must provide the URL
  protected abstract getUrl(): string;
  
  // Handlers for subclasses to override
  protected onOpen(event: Event): void {
    this.reconnectAttempts = 0;
    this.setStatus('open');
    if (this.heartbeatIntervalMs > 0) {
      this.startHeartbeat();
    }
  }
  
  protected onClose(event: CloseEvent): void {
    this.stopHeartbeat();
    this.setStatus('closed');
    if (!this.manuallyClosed) {
      this.scheduleReconnect();
    }
  }
  
  protected onMessage(event: MessageEvent): void {}
  
  protected onError(event: Event): void {
    this.setStatus('error');
  }

  protected setStatus(status: WsStatus) {
    this.status = status;
  }

  public getStatus(): WsStatus {
    return this.status;
  }

  public connect(): void {
    this.manuallyClosed = false;
    this.openSocket();
  }

  public disconnect(): void {
    this.manuallyClosed = true;
    this.clearTimers();
    this.ws?.close();
    this.ws = null;
    this.setStatus('closed');
  }

  public send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    } else {
      console.warn('BaseWebSocketManager: cannot send, socket is not open');
    }
  }

  protected openSocket(): void {
    try {
      const url = this.getUrl();
      this.ws = new WebSocket(url);
      this.setStatus('connecting');

      this.ws.onopen = (event) => this.onOpen(event);
      this.ws.onclose = (event) => this.onClose(event);
      this.ws.onmessage = (event) => this.onMessage(event);
      this.ws.onerror = (event) => this.onError(event);
    } catch (err) {
      console.error('BaseWebSocketManager: failed to create socket', err);
      this.setStatus('error');
      this.scheduleReconnect();
    }
  }

  protected scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('BaseWebSocketManager: Max WS reconnect attempts reached');
      return;
    }

    const delay = this.reconnectBaseDelayMs * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;
    console.warn(`BaseWebSocketManager: WS reconnect attempt ${this.reconnectAttempts} in ${delay}ms`);

    this.reconnectTimer = setTimeout(() => {
      if (!this.manuallyClosed) {
        this.openSocket();
      }
    }, delay);
  }

  protected startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.sendHeartbeat();
    }, this.heartbeatIntervalMs);
  }

  protected stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }
  
  protected sendHeartbeat(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }

  protected clearTimers(): void {
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
