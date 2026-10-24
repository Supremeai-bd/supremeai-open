/**
 * ComponentEventBus - Lightweight Event System for Cross-Component Communication
 * 
 * This enables your 20+ crown jewel components to talk to each other!
 * 
 * @file frontend/src/lib/componentEventBus.ts
 * @description Central event bus for SupremeAI component integration
 * @version 1.0.0
 * 
 * USAGE:
 * ```typescript
 * // Listen for events
 * useEffect(() => {
 *   return componentEventBus.on('service:status-change', (data) => {
 *     console.log(`Service ${data.service} is now ${data.status}`);
 *   });
 * }, []);
 * 
 * // Emit events
 * componentEventBus.emitServiceStatusChange('backend', 'down');
 * ```
 */

// ════════════════════════════════════════════════════════════════════
// TYPES
// ════════════════════════════════════════════════════════════════════

export type EventType = 
  // Service & Infrastructure Events
  | 'service:status-change'
  | 'service:health-update'
  | 'deployment:status-update'
  | 'deployment:complete'
  
  // Browser & Navigation Events
  | 'browser:url-changed'
  | 'browser:page-loaded'
  | 'browser:screenshot-captured'
  
  // Security Events
  | 'security:scan-complete'
  | 'security:threat-detected'
  | 'security:vulnerability-found'
  
  // AI & Intelligence Events
  | 'ai:action-complete'
  | 'ai:context-needed'
  | 'ai:insight-generated'
  
  // Memory & Knowledge Events
  | 'memory:item-created'
  | 'memory:session-saved'
  | 'memory:context-retrieved'
  
  // Alert & Notification Events
  | 'alert:new-alert'
  | 'alert:acknowledged'
  | 'alert:cleared'
  
  // User Interaction Events
  | 'user:action-performed'
  | 'user:preference-changed'
  | 'user:feedback-submitted'
  
  // Legacy Events Support
  | LegacyEventType;

export type EventCallback<T = unknown> = (data: T) => void;
export type EventDataMap = {
  'service:status-change': { service: string; status: 'healthy' | 'degraded' | 'down'; latency?: number; timestamp: number };
  'browser:url-changed': { url: string; title?: string; timestamp: number };
  'security:scan-complete': { url: string; score: number; issues: string[]; timestamp: number };
  'ai:action-complete': { action: string; result: unknown; duration: number };
  'memory:item-created': { type: string; id: string; timestamp: number };
  'alert:new-alert': { id: string; severity: string; source: string; message: string };
  'deployment:status-update': { id: string; environment: string; status: string; progress?: number };
};

// ════════════════════════════════════════════════════════════════════
// EVENT BUS CLASS
// ════════════════════════════════════════════════════════════════════

class ComponentEventBus {
  private listeners = new Map<string, Set<EventCallback<unknown>>>();
  private eventHistory: Array<{ type: string; data: unknown; timestamp: number }> = [];
  private maxHistorySize = 100;
  
  /**
   * Subscribe to an event
   * @param event - The event type to listen for
   * @param callback - Function to call when event fires
   * @returns Unsubscribe function (call to stop listening)
   */
  on<T = unknown>(event: EventType | string, callback: EventCallback<T>): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    const genericCallback = callback as EventCallback<unknown>;
    this.listeners.get(event)!.add(genericCallback);
    
    // Return unsubscribe function for cleanup
    return () => {
      this.listeners.get(event)?.delete(genericCallback);
    };
  }
  
  /**
   * Subscribe to an event only once
   * @param event - The event type to listen for
   * @param callback - Function to call when event fires (will be removed after first call)
   * @returns Unsubscribe function
   */
  subscribe<T = unknown>(event: EventType | string, callback: EventCallback<T>): () => void {
    return this.on(event, callback);
  }

  once<T = unknown>(event: EventType | string, callback: EventCallback<T>): () => void {
    const wrapper: EventCallback<T> = (data) => {
      callback(data);
      this.off(event, wrapper);
    };
    return this.on(event, wrapper);
  }
  
  /**
   * Unsubscribe from an event
   * @param event - The event type
   * @param callback - The specific callback to remove
   */
  off<T = unknown>(event: EventType | string, callback: EventCallback<T>): void {
    this.listeners.get(event)?.delete(callback as EventCallback<unknown>);
  }
  
  /**
   * Emit an event to all subscribers
   * @param event - The event type to emit
   * @param data - Optional data to pass to subscribers
   */
  emit<T = unknown>(event: EventType | string, data?: T): void {
    // Store in history for debugging
    this.eventHistory.push({ type: event, data, timestamp: Date.now() });
    if (this.eventHistory.length > this.maxHistorySize) {
      this.eventHistory.shift();
    }
    
    // Notify all listeners
    const callbacks = this.listeners.get(event);
    if (callbacks && callbacks.size > 0) {
      callbacks.forEach(cb => {
        try {
          cb(data);
        } catch (error) {
          console.error(`[ComponentEventBus] Error in handler for ${event}:`, error);
        }
      });
    }
    
    // Debug logging in development
    if (process.env.NODE_ENV === 'development') {
      console.warn(`[ComponentEventBus] 📤 ${event}`, {
        listenersCount: callbacks?.size || 0,
        data
      });
    }
  }
  
  /**
   * Remove all listeners for a specific event (or all events if no event specified)
   * @param event - Optional event type to clear
   */
  clear(event?: EventType): void {
    if (event) {
      this.listeners.delete(event);
    } else {
      this.listeners.clear();
    }
  }
  
  /**
   * Get recent event history (for debugging)
   * @param limit - Number of events to return
   */
  getHistory(limit = 20): typeof this.eventHistory {
    return this.eventHistory.slice(-limit);
  }
  
  /**
   * Get the number of listeners for a specific event
   * @param event - The event type to check
   */
  getListenerCount(event: EventType | string): number {
    return this.listeners.get(event)?.size || 0;
  }
  
  // ════════════════════════════════════════════════════════════════════
  // CONVENIENCE METHODS FOR COMMON SUPREMEAI EVENTS
  // ════════════════════════════════════════════════════════════════════
  
  /**
   * Service health status changed
   */
  emitServiceStatusChange(
    service: string, 
    status: 'healthy' | 'degraded' | 'down',
    extra?: Partial<EventDataMap['service:status-change']>
  ) {
    this.emit('service:status-change', {
      service,
      status,
      timestamp: Date.now(),
      ...extra
    });
  }
  
  /**
   * Browser URL changed (navigation)
   */
  emitBrowserUrlChange(url: string, title?: string) {
    this.emit('browser:url-changed', { url, title, timestamp: Date.now() });
  }
  
  /**
   * Security scan completed
   */
  emitSecurityScanComplete(result: {
    url: string;
    score: number;
    issues: string[];
  }) {
    this.emit('security:scan-complete', {
      ...result,
      timestamp: Date.now()
    });
    
    // Auto-trigger alert if score is low
    if (result.score < 70) {
      this.emitAlert(
        result.score < 50 ? 'critical' : 'error',
        'SecurityScanner',
        `Low security score (${result.score}/100) for ${result.url}`
      );
    }
  }
  
  /**
   * AI action completed
   */
  emitAIActionComplete(action: string, result: unknown, startTime: number) {
    this.emit('ai:action-complete', {
      action,
      result,
      duration: Date.now() - startTime
    });
  }
  
  /**
   * Memory item created/saved
   */
  emitMemoryItemCreated(type: string, id: string) {
    this.emit('memory:item-created', { type, id, timestamp: Date.now() });
  }
  
  /**
   * New alert notification
   */
  emitAlert(severity: 'info' | 'warning' | 'error' | 'critical', source: string, message: string) {
    const alertId = `alert-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    this.emit('alert:new-alert', {
      id: alertId,
      severity,
      source,
      message
    });
    
    return alertId;
  }
  
  /**
   * Deployment status updated
   */
  emitDeploymentStatusUpdate(
    id: string, 
    environment: string, 
    status: 'pending' | 'running' | 'success' | 'failed',
    progress?: number
  ) {
    this.emit('deployment:status-update', {
      id,
      environment,
      status,
      progress,
      timestamp: Date.now()
    });
    
    // Auto-emit alert for failed deployments
    if (status === 'failed') {
      this.emitAlert('error', 'DeploymentSystem', `Deployment ${id} failed in ${environment}`);
    } else if (status === 'success') {
      this.emitAlert('info', 'DeploymentSystem', `Deployment ${id} succeeded in ${environment}`);
    }
  }
}

// ════════════════════════════════════════════════════════════════════
// SINGLETON EXPORT
// ════════════════════════════════════════════════════════════════════

/**
 * Global singleton instance of the component event bus
 * Import and use anywhere in your application:
 * 
 * import { componentEventBus } from '@/lib/componentEventBus';
 */
export const componentEventBus = new ComponentEventBus();

// ════════════════════════════════════════════════════════════════════
// REACT HOOK INTEGRATION (Optional)
// ════════════════════════════════════════════════════════════════════

import { useEffect, useRef, useCallback } from 'react';

/**
 * React hook for subscribing to events with automatic cleanup
 * @param event - The event type to listen for
 * @param callback - Function to call when event fires
 * @param deps - Optional dependency array (re-subscribes when changed)
 * 
 * @example
 * ```tsx
 * const [serviceStatus, setServiceStatus] = useState('healthy');
 * useComponentEvent('service:status-change', (data) => {
 *   if (data.service === 'backend') setServiceStatus(data.status);
 * }, []);
 * ```
 */
export function useComponentEvent<T = unknown>(
  event: EventType | string, 
  callback: EventCallback<T>,
  deps: React.DependencyList = []
) {
  const callbackRef = useRef(callback);
  
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);
  
  useEffect(() => {
    return componentEventBus.on<T>(event, (data) => {
      callbackRef.current(data);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event, ...deps]);
}

/**
 * React hook for emitting events with memoized emitter
 * @returns Object with emit functions for common events
 * 
 * @example
 * ```tsx
 * const { emitAlert, emitUrlChange } = useComponentEventEmitter();
 * 
 * <button onClick={() => emitAlert('error', 'MyComponent', 'Something broke')}>
 *   Trigger Alert
 * </button>
 * ```
 */
export function useComponentEventEmitter() {
  return {
    emitServiceStatusChange: useCallback((...args: Parameters<typeof componentEventBus.emitServiceStatusChange>) => componentEventBus.emitServiceStatusChange(...args), []),
    emitBrowserUrlChange: useCallback((...args: Parameters<typeof componentEventBus.emitBrowserUrlChange>) => componentEventBus.emitBrowserUrlChange(...args), []),
    emitSecurityScanComplete: useCallback((...args: Parameters<typeof componentEventBus.emitSecurityScanComplete>) => componentEventBus.emitSecurityScanComplete(...args), []),
    emitAIActionComplete: useCallback((...args: Parameters<typeof componentEventBus.emitAIActionComplete>) => componentEventBus.emitAIActionComplete(...args), []),
    emitMemoryItemCreated: useCallback((...args: Parameters<typeof componentEventBus.emitMemoryItemCreated>) => componentEventBus.emitMemoryItemCreated(...args), []),
    emitAlert: useCallback((...args: Parameters<typeof componentEventBus.emitAlert>) => componentEventBus.emitAlert(...args), []),
    emitDeploymentStatusUpdate: useCallback((...args: Parameters<typeof componentEventBus.emitDeploymentStatusUpdate>) => componentEventBus.emitDeploymentStatusUpdate(...args), []),
    emit: useCallback((...args: Parameters<typeof componentEventBus.emit>) => componentEventBus.emit(...args), []),
  };
}

// ════════════════════════════════════════════════════════════════════
// LEGACY EVENT DEFINITIONS (Merged from eventBus.ts)
// ════════════════════════════════════════════════════════════════════

export const Events = {
  // ─── AUTHENTICATION EVENTS ────────────────────────────────
  AUTH_LOGIN: 'auth:login',
  AUTH_LOGOUT: 'auth:logout',
  AUTH_TOKEN_REFRESHED: 'auth:token_refreshed',
  AUTH_MFA_REQUIRED: 'auth:mfa_required',
  AUTH_SESSION_EXPIRED: 'auth:session_expired',

  // ─── CHAT & CONVERSATION EVENTS ──────────────────────────
  CHAT_MESSAGE_SENT: 'chat:message_sent',
  CHAT_MESSAGE_RECEIVED: 'chat:message_received',
  CHAT_CONVERSATION_CREATED: 'chat:conversation_created',
  CHAT_STREAM_START: 'chat:stream_start',
  CHAT_STREAM_TOKEN: 'chat:stream_token',
  CHAT_STREAM_END: 'chat:stream_end',
  CHAT_ERROR: 'chat:error',

  // ─── THEME & UI EVENTS ───────────────────────────────────
  THEME_CHANGED: 'theme:changed',
  THEME_DARK_MODE: 'theme:dark_mode',
  THEME_LIGHT_MODE: 'theme:light_mode',
  SIDEBAR_TOGGLED: 'ui:sidebar_toggled',
  MODAL_OPENED: 'ui:modal_opened',
  MODAL_CLOSED: 'ui:modal_closed',

  // ─── SERVICE HEALTH & MONITORING ─────────────────────────
  SERVICE_HEALTH_CHANGED: 'service:health_changed',
  SERVICE_DOWN: 'service:down',
  SERVICE_RECOVERED: 'service:recovered',
  SERVICE_DEGRADED: 'service:degraded',
  METRICS_UPDATE_AVAILABLE: 'metrics:update_available',
  METRICS_REFRESH_REQUESTED: 'metrics:refresh_requested',

  // ─── COST & BILLING EVENTS ───────────────────────────────
  COST_THRESHOLD_REACHED: 'cost:threshold_reached',
  COST_BUDGET_WARNING: 'cost:budget_warning',
  BUDGET_EXHAUSTED: 'budget:exhausted',
  TOKEN_USAGE_UPDATED: 'cost:token_usage_updated',
  PAYMENT_REQUIRED: 'payment:required',

  // ─── BROWSER EVENTS ──────────────────────────────────────
  BROWSER_URL_CHANGED: 'browser:url_changed',
  BROWSER_PAGE_LOADED: 'browser:page_loaded',
  BROWSER_PAGE_CAPTURED: 'browser:page_captured',
  BROWSER_CONTENT_INGESTED: 'browser:content_ingested',
  BROWSER_SCREENSHOT_TAKEN: 'browser:screenshot_taken',
  BROWSER_ERROR: 'browser:error',
  IFRAME_CONSOLE_ERROR: 'iframe:console_error', // For AI self-healing

  // ──��� EVOLUTION & LEARNING EVENTS ─────────────────────────
  SKILL_AUTO_CREATED: 'evolution:skill_auto_created',
  SKILL_APPROVAL_NEEDED: 'evolution:skill_approval_needed',
  PATTERN_DETECTED: 'evolution:pattern_detected',
  OPTIMIZATION_SUGGESTED: 'evolution:optimization_suggested',
  LEARNING_LOOP_COMPLETE: 'evolution:learning_complete',
  PROMPT_OPTIMIZED: 'evolution:prompt_optimized',

  // ─── SECURITY EVENTS ─────────────────────────────────────
  THREAT_DETECTED: 'security:threat_detected',
  THREAT_BLOCKED: 'security:threat_blocked',
  USER_BLOCKED: 'security:user_blocked',
  SUSPICIOUS_ACTIVITY: 'security:suspicious_activity',
  RATE_LIMIT_HIT: 'security:rate_limit_hit',

  // ─── VOICE & AUDIO EVENTS ────────────────────────────────
  VOICE_MESSAGE_READY: 'voice:message_ready',
  VOICE_TOGGLED: 'voice:toggled',
  VOICE_RECORDING_STARTED: 'voice:recording_started',
  VOICE_RECORDING_STOPPED: 'voice:recording_stopped',
  TTS_GENERATED: 'tts:generated',

  // ─── RAG & KNOWLEDGE EVENTS ──────────────────────────────
  RAG_CONTENT_UPDATED: 'rag:content_updated',
  RAG_INDEXING_COMPLETE: 'rag:indexing_complete',
  KNOWLEDGE_QUERY: 'knowledge:query',
  KNOWLEDGE_RESULT: 'knowledge:result',

  // ─── WORKSPACE & INTEGRATION EVENTS ──────────────────────
  INTEGRATION_CONNECTED: 'integration:connected',
  INTEGRATION_DISCONNECTED: 'integration:disconnected',
  WORKSPACE_CHANGED: 'workspace:changed',
  FILE_SAVED: 'workspace:file_saved',
  DEPLOYMENT_STATUS: 'deployment:status',

  // ─── ADMIN-SPECIFIC EVENTS ───────────────────────────────
  USER_ACTION_LOGGED: 'admin:user_action',
  SETTINGS_CHANGED: 'admin:settings_changed',
  BACKUP_COMPLETED: 'admin:backup_completed',
  SYSTEM_ALERT: 'admin:system_alert',

  // ─── HITL (HUMAN-IN-THE-LOOP) EVENTS ────────────────────
  HITL_REQUIRED: 'hitl:required',
  HITL_SESSION_STARTED: 'hitl:session_started',
  HITL_SESSION_ENDED: 'hitl:sessionEnded',
  TAKEOVER_REQUESTED: 'hitl:takeover_requested',
  CONTROL_RETURNED: 'hitl:control_returned',
} as const;

// Export legacy event types and alias
export type LegacyEventType = typeof Events[keyof typeof Events];
export const eventBus = componentEventBus;
export default componentEventBus;
