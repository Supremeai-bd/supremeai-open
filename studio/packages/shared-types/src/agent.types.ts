/**
 * এজেন্ট অ্যাকশন — এজেন্ট বর্তমানে যে নির্দিষ্ট টুল বা অভ্যন্তরীণ কাজটি
 * সম্পাদন করছে তা নির্দেশ করে।
 */
export type AgentAction =
  | 'READ_FILE'
  | 'WRITE_FILE'
  | 'RUN_COMMAND'
  | 'SEARCH_CODEBASE'
  | 'ANALYZE_ERROR'
  | 'RUN_SANDBOX'
  | 'IDLE';

/**
 * এজেন্ট রিজনিং — AI-এর অভ্যন্তরীণ চিন্তাশৃঙ্খল (chain-of-thought) ধারণ করে।
 * এজেন্ট কী ভাবছে তা দেখানোর জন্য এটি UI-তে স্ট্রিম বা রিটার্ন করা হয়।
 */
export interface AgentReasoning {
  stepIndex: number;
  chainOfThought: string;
  confidenceScore: number; // আত্মবিশ্বাসের মাত্রা: ০.০ থেকে ১.০ পর্যন্ত
  toolCallSuggestion?: AgentAction; // পরবর্তী টুল কলের জন্য প্রস্তাবনা
  contextUsed?: string[]; // এই রিজনিং ধাপে ব্যবহৃত ফাইল বা কনটেক্সট চাঙ্ক
}

/**
 * এজেন্টের সব রেসপন্সের জন্য একীভূত (unified) এনভেলপ কাঠামো।
 */
export interface AgentResponse<T = any> {
  reasoningLog: AgentReasoning[];
  executedActions: { action: AgentAction; status: 'SUCCESS' | 'FAILED' | 'PENDING'; detail?: string }[];
  finalOutput: T;
  timestamp: string;
}
