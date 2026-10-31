// Voice speech synthesizer helper for desktop/browser
export function speakText(text: string) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return;
  try {
    window.speechSynthesis.cancel(); // Stop any ongoing speech
    // Clean markdown symbols for cleaner voice speech
    const cleanText = text
      .replace(/[*_#`[\]()]/g, '')
      .replace(/https?:\/\/\S+/g, 'link')
      .trim();

    if (!cleanText) return;
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.05;
    utterance.pitch = 1.0;

    // Pick a natural English voice if available
    const voices = window.speechSynthesis.getVoices();
    const naturalVoice = voices.find(
      (v) =>
        v.lang.startsWith('en') &&
        (v.name.includes('Natural') || v.name.includes('Neural') || v.name.includes('Google') || v.name.includes('Zira') || v.name.includes('David'))
    );
    if (naturalVoice) utterance.voice = naturalVoice;

    window.speechSynthesis.speak(utterance);
  } catch (err) {
    console.error('Speech synthesis error:', err);
  }
}

// Fallback intelligent agent response generator for offline / browser preview mode
export function generateLocalReply(prompt: string): string {
  const p = prompt.toLowerCase();
  if (p.includes('hello') || p.includes('hi') || p.includes('hey')) {
    return 'Greetings! SupremeAI Neural Core is online and synchronizing telemetry. How can I assist your operations today?';
  }
  if (p.includes('status') || p.includes('health') || p.includes('system')) {
    return 'All internal systems are operating nominally. Edge database latency is 24ms, Swarm cluster nodes are green, and security guards are active.';
  }
  if (p.includes('who are you') || p.includes('what are you')) {
    return 'I am the SupremeAI Holographic Assistant, your paired neural companion for autonomous workflows, code verification, and real-time system management.';
  }
  if (p.includes('help') || p.includes('task')) {
    return 'I can help inspect codebases, execute verification ladders, monitor platform clusters, or assist in system design. Speak or type your instruction.';
  }
  return `Acknowledged request: "${prompt}". Processing instruction through local holographic orchestration. All federation parameters remain within nominal limits.`;
}

