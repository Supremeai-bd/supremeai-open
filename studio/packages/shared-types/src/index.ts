// শেয়ার্ড টাইপ প্যাকেজের কেন্দ্রীয় এক্সপোর্ট (barrel) ফাইল।
// ব্যাকএন্ড ও ফ্রন্টএন্ড উভয়ই এখান থেকে অভিন্ন টাইপ আমদানি করে,
// ফলে দুই পাশে টাইপ সংজ্ঞা আলাদা হয়ে যাওয়ার ঝুঁকি থাকে না।
export { MessageSchema, ChatRoleSchema, CHAT_ROLES, type Message, type ChatRole, type ToolCallRecord } from './message';
export { ConversationSchema, type Conversation } from './conversation';
export type { Skill } from './conversation';
export type { ToolCall } from './conversation';
export type { ApiResponse } from './conversation';
// Unified chat contract (DRY Phase 1-B1) — frontend এখান থেকে re-export করে।
export * from './chat';
export * from './agent.types';
export * from './auth.types';
