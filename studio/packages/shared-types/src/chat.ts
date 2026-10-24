/**
 * Unified chat contract — মোনোরিপোর একক সত্যের উৎস (DRY Phase 1-B1)।
 *
 * আগে এই সংজ্ঞাগুলো frontend/src/types/chat.ts-এ বাস করত এবং ফাইলের হেডারে
 * "Single Source of Truth" লেখা থাকলেও প্যাকেজ বাইপাস করে লোকাল ডুপ্লিকেট
 * হিসেবেই থাকত — ফলে @supremeai/shared-types (৩ role) আর frontend (৬ role)
 * আলাদা হয়ে drift করত। এখন কাঠামোটা এখানে থাকে; frontend ফাইলটি এখান থেকে
 * re-export করে, তাই ব্যাকএন্ড ↔ ফ্রন্টএন্ড contract কখনোই আলাদা হতে পারে না।
 */

import type { ChatRole } from './message';

// ═══════════════════════════════════════════════════════════════
// CORE CHAT TYPES
// ═══════════════════════════════════════════════════════════════

export interface UnifiedChatMessage {
  id?: string;
  role: ChatRole;
  content: string;
  timestamp?: number | string;
  /** Legacy aliases accepted at UI boundaries while callers migrate. */
  sender?: string;
  text?: string;
  action?: string;
  project_id?: string;
  metadata?: MessageMetadata;
}

export type { ChatRole };

export interface MessageMetadata {
  model?: string;
  provider?: string;
  tokens?: number;
  cost?: number;
  /** Where did this message originate from? */
  source?: MessageSource;
  /** Parent message ID for threading/replies */
  parentId?: string;
  /** Was this message edited? */
  editedAt?: number;
  /** Attachments (files, images, etc.) */
  attachments?: Attachment[];
}

export type MessageSource =
  | 'chat'           // Direct user chat
  | 'evolution'      // AI self-evolution
  | 'browser'        // Browser agent context
  | 'voice'          // Voice input transcribed
  | 'swarm'          // Multi-agent swarm
  | 'api'            // External API call
  | 'import';        // Imported conversation

export interface Attachment {
  id: string;
  type: 'image' | 'file' | 'code' | 'url';
  name: string;
  url: string;
  size?: number;
  mimeType?: string;
}

// ═══════════════════════════════════════════════════════════════
// CONVERSATION TYPES
// ═══════════════════════════════════════════════════════════════

export interface ChatConversation {
  id: string;
  title: string;
  messages: UnifiedChatMessage[];
  createdAt: number;
  updatedAt: number;
  /** User-defined tags for organization */
  tags?: string[];
  /** Is this conversation pinned? */
  isPinned?: boolean;
  /** Associated workspace/project ID */
  workspaceId?: string;
  /** Conversation metadata */
  metadata?: ConversationMetadata;
}

export interface ConversationMetadata {
  totalTokens: number;
  totalCost: number;
  messageCount: number;
  lastModelUsed?: string;
  /** RAG context used */
  ragSources?: string[];
}

// ═══════════════════════════════════════════════════════════════
// HELPER TYPES
// ═══════════════════════════════════════════════════════════════

export interface ChatState {
  conversations: ChatConversation[];
  activeConversationId: string | null;
  isLoading: boolean;
  error: string | null;
}

export interface SendMessagePayload {
  content: string;
  conversationId?: string;
  attachments?: Attachment[];
  metadata?: Partial<MessageMetadata>;
}

export interface StreamChunkPayload {
  token: string;
  messageId: string;
  isComplete: boolean;
  metadata?: Partial<MessageMetadata>;
}

// Type guards
export function isUserMessage(msg: UnifiedChatMessage): boolean {
  return msg.role === 'user';
}

export function isAssistantMessage(msg: UnifiedChatMessage): boolean {
  return msg.role === 'assistant' || msg.role === 'ai';
}

export function hasAttachments(msg: UnifiedChatMessage): boolean {
  return (msg.metadata?.attachments?.length ?? 0) > 0;
}
