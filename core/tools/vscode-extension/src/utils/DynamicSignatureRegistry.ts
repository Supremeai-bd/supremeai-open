export class DynamicSignatureRegistry {
  private static instance: DynamicSignatureRegistry;
  private signatures: Map<string, string[]> = new Map();

  private constructor() {
    this.loadDefaultSignatures();
    // async loadFromConfig কে fire-and-forget বলা হচ্ছে (await না করা হলে config পরে load হবে)
    this.loadFromConfig().then(() => {
      console.debug('[SupremeAI] Dynamic signatures loaded from config.');
    }).catch(err => {
      console.debug('Using default signatures', err);
    });
  }

  static getInstance(): DynamicSignatureRegistry {
    if (!DynamicSignatureRegistry.instance) {
      DynamicSignatureRegistry.instance = new DynamicSignatureRegistry();
    }
    return DynamicSignatureRegistry.instance;
  }

  loadDefaultSignatures(): void {
    this.signatures.set('GREETING_PATTERNS', [
      'hello', 'hi', 'hey', 'greetings', 'hola', 'good morning', 'good afternoon', 'good evening',
      'assalamualaikum', 'namaste', 'হ্যালো', 'হাই', 'নমস্কার', 'কেমন আছেন', 'শুভ সকাল'
    ]);
    this.signatures.set('DEBUG_PATTERNS', [
      'bug', 'error', 'fix', 'debug', 'issue', 'problem', 'crash'
    ]);
    this.signatures.set('REFACTOR_PATTERNS', [
      'refactor', 'improve', 'optimize', 'cleanup', 'restructure'
    ]);
    this.signatures.set('EXPLAIN_PATTERNS', [
      'explain', 'understand', 'clarify', 'what is', 'how does', 'tell me'
    ]);
    this.signatures.set('TIME_PATTERNS', [
      'time', 'current time', 'what time', 'hour', 'clock'
    ]);
    this.signatures.set('GREETING_RESPONSES', [
      'Hello! I\'m SupremeAI, your autonomous coding assistant. How can I help you today?',
      'হ্যালো! আমি সুপ্রিমএআই, আপনার স্বয়ংক্রিয় কোডিং সহকারী। আমি আজ আপনাকে কিভাবে সাহায্য করতে পারি?',
      'নমস্কার! আমি সুপ্রিমএআই। আপনার কোডিং যাত্রায় সাহায্য করতে প্রস্তুত।'
    ]);
    this.signatures.set('DEBUG_RESPONSES', [
      'I can help you debug! Please share the error message or the problematic code, and I\'ll analyze it.'
    ]);
    this.signatures.set('REFACTOR_RESPONSES', [
      'I can help refactor your code! Please share the code you\'d like to improve.'
    ]);
    this.signatures.set('EXPLAIN_RESPONSES', [
      'I can explain code concepts! Please share the code or concept you\'d like me to explain.'
    ]);
    this.signatures.set('TIME_RESPONSES', [
      'The current time is: {{time}}'
    ]);
    this.signatures.set('DEFAULT_RESPONSES', [
      'I\'m here to help with your coding needs!'
    ]);
    this.signatures.set('FALLBACK_MESSAGES', [
      'I\'m here to help with your coding needs!'
    ]);
  }

  async loadFromConfig(): Promise<void> {
    try {
      const vscode = await import('vscode');
      const config = vscode.workspace.getConfiguration('supremeai');
      const dynamicConfig = config.get<any>('dynamicSignatures');

      if (dynamicConfig && typeof dynamicConfig === 'object') {
        Object.entries(dynamicConfig).forEach(([key, value]) => {
          if (Array.isArray(value) && value.every(v => typeof v === 'string')) {
            this.signatures.set(key, value as string[]);
          }
        });
      }
    } catch (error) {
      console.debug('Using default signatures', error);
    }
  }

  matchesAny(input: string, group: string): boolean {
    const patterns = this.signatures.get(group);
    if (!patterns) return false;
    return patterns.some(pattern => input.includes(pattern.toLowerCase()));
  }

  getTemplates(group: string): string[] {
    return this.signatures.get(group) || [];
  }

  registerSignature(group: string, pattern: string): void {
    const existing = this.signatures.get(group) || [];
    if (!existing.includes(pattern)) {
      this.signatures.set(group, [...existing, pattern]);
    }
  }

  detectCategory(input: string): string {
    for (const [group, patterns] of this.signatures.entries()) {
      if (group.endsWith('_PATTERNS') && patterns.some(p => input.includes(p.toLowerCase()))) {
        return group.replace('_PATTERNS', '');
      }
    }
    return 'GENERAL';
  }
}
