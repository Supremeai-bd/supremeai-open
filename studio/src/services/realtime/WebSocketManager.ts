import { BaseWebSocketManager, type BaseWebSocketManagerOptions } from '@supremeai/shared-services';

export interface WebSocketManagerHandlers {
  onOpen?: (event: Event) => void;
  onClose?: (event: CloseEvent) => void;
  onMessage?: (event: MessageEvent) => void;
  onError?: (event: Event) => void;
}

export interface WebSocketManagerOptions extends BaseWebSocketManagerOptions, WebSocketManagerHandlers {}

export default class WebSocketManager extends BaseWebSocketManager {
  private url: string;
  private handlers: WebSocketManagerHandlers;

  constructor(url: string, options: WebSocketManagerOptions = {}) {
    super(options);
    this.url = url;
    
    // We pass only handlers to store them
    const { maxReconnectAttempts: _maxReconnectAttempts, reconnectBaseDelayMs: _reconnectBaseDelayMs, heartbeatIntervalMs: _heartbeatIntervalMs, ...handlers } = options;
    this.handlers = handlers;
  }

  protected getUrl(): string {
    return this.url;
  }

  protected onOpen(event: Event): void {
    super.onOpen(event);
    this.handlers.onOpen?.(event);
  }

  protected onClose(event: CloseEvent): void {
    super.onClose(event);
    this.handlers.onClose?.(event);
  }

  protected onMessage(event: MessageEvent): void {
    super.onMessage(event);
    this.handlers.onMessage?.(event);
  }

  protected onError(event: Event): void {
    super.onError(event);
    this.handlers.onError?.(event);
  }
}
