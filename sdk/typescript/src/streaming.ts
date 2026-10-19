/**
 * @supremeai/sdk — SSE chunk parser and tool call re-assembly.
 *
 * Handles multi-line data fields, CRLF/LF line endings, interleaved
 * id/event lines, and the [DONE] sentinel. Tool call deltas are stitched
 * back into complete calls by index (id + name + concatenated argument
 * fragments).
 */

import type { StreamEvent, ToolCallDelta } from './types/generated.ts';

export interface AssembledToolCall {
  index: number;
  id: string;
  name: string;
  arguments: string;
}

export class SSEParser {
  private buffer = '';
  private dataLines: string[] = [];
  private eventName = '';
  private eventId?: string;

  /** Feed raw text; returns the events completed by this chunk. */
  push(chunk: string): StreamEvent[] {
    this.buffer += chunk;
    const events: StreamEvent[] = [];
    let newlineAt = this.buffer.search(/\r?\n/);
    while (newlineAt !== -1) {
      const line = this.buffer.slice(0, newlineAt);
      this.buffer = this.buffer.slice(
        newlineAt + (this.buffer[newlineAt] === '\r' && this.buffer[newlineAt + 1] === '\n' ? 2 : 1),
      );
      const emitted = this.consumeLine(line);
      if (emitted) {
        events.push(emitted);
      }
      newlineAt = this.buffer.search(/\r?\n/);
    }
    return events;
  }

  /** Flush any pending event at end-of-stream. */
  finish(): StreamEvent[] {
    const flushed = this.flushEvent();
    this.buffer = '';
    return flushed ? [flushed] : [];
  }

  private consumeLine(line: string): StreamEvent | undefined {
    if (line === '') {
      return this.flushEvent();
    }
    if (line.startsWith(':')) {
      return undefined; // comment / keep-alive
    }
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) {
      value = value.slice(1);
    }
    if (field === 'data') {
      this.dataLines.push(value);
    } else if (field === 'event') {
      this.eventName = value;
    } else if (field === 'id') {
      this.eventId = value;
    }
    return undefined;
  }

  private flushEvent(): StreamEvent | undefined {
    if (this.dataLines.length === 0 && this.eventName === '') {
      return undefined;
    }
    const data = this.dataLines.join('\n');
    const event: StreamEvent = {
      event: this.eventName || 'message',
      data,
    };
    if (this.eventId !== undefined) {
      event.id = this.eventId;
    }
    if (data !== '[DONE]') {
      try {
        event.parsed = JSON.parse(data);
      } catch {
        /* non-JSON data — parsed stays undefined */
      }
    }
    this.dataLines = [];
    this.eventName = '';
    this.eventId = undefined;
    return event;
  }
}

/** Accumulator stitching ToolCallDelta fragments into complete calls. */
export class ToolCallAssembler {
  private readonly partials = new Map<number, AssembledToolCall>();

  add(delta: ToolCallDelta): AssembledToolCall | undefined {
    const current =
      this.partials.get(delta.index) ??
      { index: delta.index, id: '', name: '', arguments: '' };
    if (delta.id) {
      current.id = delta.id;
    }
    if (delta.name) {
      current.name = delta.name;
    }
    if (delta.argumentsFragment) {
      current.arguments += delta.argumentsFragment;
    }
    this.partials.set(delta.index, current);
    return current;
  }

  /** Snapshot of assembled calls; argument JSON validity is caller-checked. */
  list(): AssembledToolCall[] {
    return [...this.partials.values()].sort((a, b) => a.index - b.index);
  }
}

type ResponseFactory = () => Promise<Response>;

/**
 * Bridge a fetch Response SSE body into an async iterable of parsed
 * StreamEvents. disposer() is invoked when iteration ends or throws.
 */
export async function* streamRunEvents(
  start: ResponseFactory,
  disposer?: () => void,
): AsyncIterable<StreamEvent> {
  const response = await start();
  if (!response.body) {
    disposer?.();
    return;
  }
  const parser = new SSEParser();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      for (const event of parser.push(decoder.decode(value, { stream: true }))) {
        if (event.data === '[DONE]') {
          return;
        }
        yield event;
      }
    }
    for (const event of parser.push(decoder.decode())) {
      if (event.data === '[DONE]') {
        return;
      }
      yield event;
    }
    for (const event of parser.finish()) {
      if (event.data === '[DONE]') {
        return;
      }
      yield event;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* reader already closed */
    }
    disposer?.();
  }
}
