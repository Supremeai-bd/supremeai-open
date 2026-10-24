import { z } from 'zod';

/**
 * অথেনটিকেশন স্টেট — ইউজারের লগইন অবস্থার তিনটি সম্ভাব্য ধাপ।
 * UNINITIALIZED: অ্যাপ এখনো সেশন যাচাই করেনি (লোডিং অবস্থা)।
 * এই ধাপটি আলাদা রাখা জরুরি, নাহলে সেশন রিস্টোর হওয়ার আগেই
 * ইউজারকে ভুলভাবে লগআউট অবস্থায় দেখানো হবে।
 */
export const AuthStateEnum = z.enum([
  'UNINITIALIZED',
  'LOGGED_OUT',
  'LOGGED_IN'
]);

/**
 * অথ ট্রানজিশন ইভেন্ট — যেসব ঘটনার কারণে অথ স্টেট এক ধাপ থেকে
 * অন্য ধাপে পরিবর্তিত হয়।
 */
export const AuthTransitionEventEnum = z.enum([
  'AUTH_INIT',
  'LOGIN_SUCCESS',
  'LOGIN_FAILURE',
  'SESSION_RESTORE',
  'LOGOUT',
  'SESSION_EXPIRE',
  'WORKSPACE_SWITCH'
]);

/**
 * ওয়ার্কস্পেস স্টেট — লগইন করা ইউজার বর্তমানে অ্যাপের কোন অংশে আছেন।
 */
export const WorkspaceStateEnum = z.enum([
  'DASHBOARD',
  'PROJECT_SPACE',
  'SETTINGS',
  'COLLABORATION'
]);

/**
 * অথ স্টেট স্কিমা — সম্পূর্ণ অথেনটিকেশন অবস্থার কাঠামো।
 * লগআউট অবস্থায় user, activeWorkspaceId ও workspaceState null থাকে,
 * তাই এগুলো nullable হিসেবে সংজ্ঞায়িত করা হয়েছে।
 */
export const AuthStateSchema = z.object({
  status: AuthStateEnum,
  user: z.object({
    id: z.string(),
    email: z.string().email(),
    role: z.string()
  }).nullable(),
  activeWorkspaceId: z.string().nullable(),
  workspaceState: WorkspaceStateEnum.nullable()
});

export type AuthState = z.infer<typeof AuthStateEnum>;
export type AuthTransitionEvent = z.infer<typeof AuthTransitionEventEnum>;
export type WorkspaceState = z.infer<typeof WorkspaceStateEnum>;
export type AuthStateData = z.infer<typeof AuthStateSchema>;
