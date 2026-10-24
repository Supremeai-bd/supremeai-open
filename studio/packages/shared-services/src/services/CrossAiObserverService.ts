/**
 * CrossAiObserverService — কাছের AI agents (Copilot, Gemini, Kilo, Cline, aider, ইত্যাদি)
 * এর কার্যক্রম পর্যবেক্ষণ করে evolution/learn endpoint-এ পাঠায় (platform-agnostic)।
 */

/**
 * অন্যান্য AI এজেন্ট চালু আছে কিনা সনাক্ত করার হিউরিস্টিক।
 * Desktop Electron-এ আমরা system clipboard / active window টাইটেল এ area ব্যবহার করতে পারি;
 * VS Code-এ terminals অথবা settings স্ক্যান করা হয়।
 */
const AGENT_KEYWORDS = ['copilot', 'gemini', 'kilo', 'cline', 'aider', 'continue', 'cursor', 'windsurf'];

export class CrossAiObserverService {
  // বাংলা মন্তব্য (#3078): মৃত Cloud Run host সরানো — ডিফল্ট খালি; backendUrl না পেলে
  // reportLearning স্পষ্ট সতর্কতাসহ স্কিপ করবে (নীরব মৃত-host POST নয়)।
  private static _backendUrl = '';
  private static _warnedNoBackend = false;

  public static initialize(): void {
    // eslint-disable-next-line no-console
    console.log('📡 [Cross-AI Observer] Standby Mode.');
  }

  /** কিছু টেক্সটে agent-activity আভাস খোঁজে। */
  public static isAgenticActivity(text: string): boolean {
    const lower = text.toLowerCase();
    return AGENT_KEYWORDS.some((kw) => lower.includes(kw));
  }

  /** ডেটাবেজে লার্নিং রিপোর্ট পাঠায়। */
  public static async reportLearning(opts: {
    type: string;
    approach: string;
    result: string;
    token?: string | null;
    backendUrl?: string;
  }): Promise<void> {
    const { type, approach, result, token, backendUrl } = opts;
    const url = backendUrl || CrossAiObserverService._backendUrl;
    if (!url) {
      // বাংলা মন্তব্য (#3078): backendUrl অনুপস্থিত — একবারই সতর্ক করে স্কিপ (graceful degradation)।
      if (!CrossAiObserverService._warnedNoBackend) {
        CrossAiObserverService._warnedNoBackend = true;
        // eslint-disable-next-line no-console
        console.warn(
          '📡 [Cross-AI Observer] backendUrl অনুপস্থিত — learning-report স্কিপ করা হচ্ছে (#3078: মৃত Cloud Run ডিফল্ট সরানো হয়েছে)।'
        );
      }
      return;
    }
    try {
      const payload = {
        task: `Observed local device activity of type: ${type}`,
        approach,
        result,
        timestamp: new Date().toISOString(),
      };
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      await (await fetch(url, { method: 'POST', headers, body: JSON.stringify(payload) })).json();
      // eslint-disable-next-line no-console
      console.log('💾 [Cross-AI Learned] Intercepted workflow synced to Supreme Database Pool.');
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('❌ Failed to stream cross-AI observed metrics to backend:', error);
    }
  }
}