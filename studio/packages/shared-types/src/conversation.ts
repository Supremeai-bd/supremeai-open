import { z } from 'zod';
import { MessageSchema } from './message';

/**
 * স্কিল স্কিমা — এজেন্টের একটি সক্ষমতা বা দক্ষতা মডিউল।
 * enabled ফ্ল্যাগ দিয়ে কোনো স্কিল রানটাইমে চালু/বন্ধ করা যায়, ডিফল্টে চালু থাকে।
 */
export const SkillSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  version: z.string(),
  enabled: z.boolean().default(true),
});

export type Skill = z.infer<typeof SkillSchema>;

/**
 * কনভারসেশন স্কিমা — একটি সম্পূর্ণ কথোপকথন সেশন।
 * এতে ধারাবাহিক বার্তা, সেশনে সক্রিয় স্কিলসমূহ এবং সময়ের তথ্য থাকে।
 */
export const ConversationSchema = z.object({
  id: z.string(),
  messages: z.array(MessageSchema),
  skills: z.array(SkillSchema).optional(),
  createdAt: z.date(),
  updatedAt: z.date(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export type Conversation = z.infer<typeof ConversationSchema>;

/**
 * API রেসপন্স স্কিমা — সব API রেসপন্সের অভিন্ন কাঠামো।
 * success সফলতা নির্দেশ করে; ব্যর্থ হলে error অবজেক্টে কোড ও বার্তা থাকে।
 * requestId দিয়ে লগে অনুরোধটি ট্রেস করা যায়।
 */
export const ApiResponseSchema = z.object({
  success: z.boolean(),
  data: z.unknown().optional(),
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.string(), z.unknown()).optional(),
  }).optional(),
  requestId: z.string().optional(),
});

/**
 * ApiResponse — উপরের স্কিমার জেনেরিক টাইপ সংস্করণ।
 * T দিয়ে প্রতিটি এন্ডপয়েন্ট তার নিজস্ব ডেটা টাইপ নির্দিষ্ট করতে পারে।
 */
export type ApiResponse<T = unknown> = {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  requestId?: string;
};

/**
 * ToolCall — LLM থেকে আসা ফাংশন কল অনুরোধের গঠন।
 * arguments একটি JSON স্ট্রিং হিসেবে আসে, ব্যবহারের আগে পার্স করতে হয়।
 */
export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}
