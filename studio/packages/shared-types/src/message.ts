import { z } from 'zod';

/**
 * টুল কল স্কিমা — এজেন্ট কোনো টুল চালালে সেই কলের পরিচয়, ইনপুট আর্গুমেন্ট,
 * ফলাফল এবং বর্তমান অবস্থা এখানে ধারণ করা হয়।
 */
export const ToolCallSchema = z.object({
  id: z.string(),
  name: z.string(),
  arguments: z.record(z.string(), z.unknown()),
  result: z.string().optional(),
  // status: টুলটি এখনো চলছে (pending), সফল হয়েছে (success) নাকি ব্যর্থ (error)
  status: z.enum(['pending', 'success', 'error']),
});

export type ToolCallRecord = z.infer<typeof ToolCallSchema>;

/**
 * ChatRole — মোনোরিপো-ব্যাপী একক সত্যের উৎস (SSOT)।
 *
 * DRY Phase 1-B1: আগে shared-types-এ ৩ role, frontend-এ ৬ role ছিল —
 * contract drift হয়েছিল। এখন এই enum-ই সুপারসেট; ব্যাকএন্ড, ফ্রন্টএন্ড ও
 * এক্সটেনশন সবাই এখান থেকে নেয়।
 *   user / assistant / ai  — কথোপকথনের পক্ষ ('ai' কিছু পুরনো স্টোরের legacy)
 *   system                 — সিস্টেম নির্দেশনা
 *   tool / function        — টুল ও ফাংশন-কল ফলাফল
 */
export const CHAT_ROLES = ['user', 'assistant', 'ai', 'system', 'tool', 'function'] as const;

export const ChatRoleSchema = z.enum(CHAT_ROLES);

export type ChatRole = z.infer<typeof ChatRoleSchema>;

/**
 * মেসেজ স্কিমা — কথোপকথনের একটি একক বার্তা (পার্সিং-বান্ধব কঠোর সংস্করণ)।
 *
 * frontend/src/types/chat.ts-এর UnifiedChatMessage-এর সুপারসেট:
 * - id ঐচ্ছিক (UI অস্থায়ী বার্তায় id পরে বসায়)
 * - timestamp: Date | number | string (epoch ms ও ISO স্ট্রিং উভয়ই আসে)
 * - sender/text/action/project_id legacy alias — সীমানায় গ্রহণ করা হয়
 * - metadata মেসেজ-স্তরের অতিরিক্ত তথ্য বহন করে
 * অ্যাসিস্ট্যান্ট টুল ব্যবহার করলে সেগুলো toolCalls-এ সংযুক্ত থাকে।
 */
export const MessageSchema = z.object({
  id: z.string().optional(),
  role: ChatRoleSchema,
  content: z.string(),
  timestamp: z.union([z.date(), z.number(), z.string()]).optional(),
  toolCalls: z.array(ToolCallSchema).optional(),
  /** Legacy aliases accepted at UI boundaries while callers migrate. */
  sender: z.string().optional(),
  text: z.string().optional(),
  action: z.string().optional(),
  project_id: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export type Message = z.infer<typeof MessageSchema>;
