/**
 * Unified chat types — RE-EXPORT SHELL (DRY Phase 1-B1).
 *
 * প্রকৃত সংজ্ঞা এখন @supremeai/shared-types-এ বাস করে (packages/shared-types/
 * src/chat.ts + message.ts) — ব্যাকএন্ড, ফ্রন্টএন্ড ও এক্সটেনশন সবাই একই
 * contract থেকে টাইপ নেয়; ৩-role বনাম ৬-role drift আর সম্ভব নয়।
 *
 * এই ফাইলের পাথ অপরিবর্তিত রাখা হয়েছে যাতে বিদ্যমান importer-রা
 * ('@/types/chat', '../types/chat' ইত্যাদি) অক্ষত থাকে।
 */

export type {
  UnifiedChatMessage,
  ChatRole,
  MessageMetadata,
  MessageSource,
  Attachment,
  ChatConversation,
  ConversationMetadata,
  ChatState,
  SendMessagePayload,
  StreamChunkPayload,
} from '@supremeai/shared-types';

export {
  isUserMessage,
  isAssistantMessage,
  hasAttachments,
} from '@supremeai/shared-types';
