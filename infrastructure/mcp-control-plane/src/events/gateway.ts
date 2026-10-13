import { NormalizedEvent } from "./normalizer.js";

type EventListener = (event: NormalizedEvent) => void | Promise<void>;

export class EventGateway {
  private listeners: EventListener[] = [];
  private eventHistory: NormalizedEvent[] = [];

  /**
   * Registers a listener for all events.
   */
  public subscribe(listener: EventListener): void {
    this.listeners.push(listener);
  }

  /**
   * Dispatches a normalized event to all listeners.
   */
  public async dispatch(event: NormalizedEvent): Promise<void> {
    this.eventHistory.push(event);
    if (this.eventHistory.length > 100) {
      this.eventHistory.shift(); // Keep last 100 events
    }

    console.log(`[EVENT GATEWAY] Received [${event.severity}] from ${event.source}: ${event.message}`);

    // Fire all listeners asynchronously without waiting for them to finish
    // (Fire and forget, but catch unhandled rejections)
    for (const listener of this.listeners) {
      Promise.resolve(listener(event)).catch((err) => {
        console.error(`[EVENT GATEWAY] Listener error: ${err.message}`);
      });
    }
  }

  /**
   * Retrieves recent events.
   */
  public getHistory(): NormalizedEvent[] {
    return this.eventHistory;
  }
}

export const globalEventGateway = new EventGateway();
