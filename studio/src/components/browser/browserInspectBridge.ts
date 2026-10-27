export interface ElementMeta {
  selector: string;
  tag: string;
  id?: string;
  className?: string;
  text?: string;
  attributes?: Record<string, string>;
}

export function elementToSelector(el: Element | null): string {
  if (!el) return '';
  const tag = el.tagName.toLowerCase();
  if (el.id) return `#${el.id}`;
  const classes = Array.from(el.classList).slice(0, 2).join('.');
  if (classes) return `${tag}.${classes}`;
  const parent = el.parentElement;
  if (parent) {
    const siblings = Array.from(parent.children).filter((c) => c.tagName === el.tagName);
    const idx = siblings.indexOf(el) + 1;
    return `${tag}:nth-of-type(${idx})`;
  }
  return tag;
}

export function inspectElement(el: Element | null): ElementMeta {
  if (!el) return { selector: '', tag: '' };
  const attrs: Record<string, string> = {};
  for (let i = 0; i < el.attributes.length; i++) {
    const a = el.attributes[i];
    attrs[a.name] = a.value;
  }
  return {
    selector: elementToSelector(el),
    tag: el.tagName.toLowerCase(),
    id: el.id || undefined,
    className: el.className || undefined,
    text: (el.textContent || '').trim().slice(0, 120),
    attributes: attrs,
  };
}

export type InspectCallback = (meta: ElementMeta) => void;

export function createInspectHandler(onInspect: InspectCallback): (e: MouseEvent) => void {
  return (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const target = e.target as Element | null;
    onInspect(inspectElement(target));
  };
}

export interface ConsoleBridgeMessage {
  type: 'log' | 'error' | 'warn' | 'info';
  message: string;
  source?: string;
  line?: number;
  column?: number;
  timestamp: number;
}

export function listenConsoleMessages(cb: (msg: ConsoleBridgeMessage) => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const handler = (event: MessageEvent) => {
    if (event.data?.source !== 'iframe-console') return;
    cb({
      type: event.data.type ?? 'log',
      message: String(event.data.message ?? ''),
      source: event.data.source,
      line: event.data.line,
      column: event.data.column,
      timestamp: Date.now(),
    });
  };
  window.addEventListener('message', handler);
  return () => window.removeEventListener('message', handler);
}

export function injectConsoleTrap(iframe: HTMLIFrameElement | null): void {
  if (!iframe?.contentWindow) return;
  try {
    const targetOrigin = iframe.src && iframe.src !== 'about:blank'
      ? new URL(iframe.src, window.location.href).origin
      : window.location.origin;
    iframe.contentWindow.postMessage({ type: 'CONSOLE_TRAP_INIT' }, targetOrigin);
  } catch {
    // ignore
  }
}

export function formatInspectTag(meta: ElementMeta): string {
  return `[Inspecting: <${meta.tag}${meta.id ? '#' + meta.id : ''}${meta.className ? '.' + meta.className.split(' ')[0] : ''}>]`;
}

const browserInspectBridge = {
  inspectElement,
  elementToSelector,
  createInspectHandler,
  listenConsoleMessages,
  injectConsoleTrap,
  formatInspectTag,
};

export { browserInspectBridge };
export default browserInspectBridge;