/**
 * High-Tech Web Audio Sound Engine for JARVIS & Companion Hologram
 * Pure browser-native synthesis with zero external MP3 dependencies.
 */

class JarvisAudioEngine {
  private ctx: AudioContext | null = null;
  public soundEnabled: boolean = true;
  private visemeTimer: any = null;

  private initContext() {
    if (!this.ctx && typeof window !== 'undefined') {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  /**
   * Stark HUD Activation Chime (Two-tone ascending crystalline chime)
   */
  playActivate() {
    if (!this.soundEnabled) return;
    try {
      this.initContext();
      if (!this.ctx) return;
      const now = this.ctx.currentTime;

      const osc1 = this.ctx.createOscillator();
      const osc2 = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc1.type = 'sine';
      osc2.type = 'triangle';

      osc1.frequency.setValueAtTime(587.33, now); // D5
      osc1.frequency.exponentialRampToValueAtTime(880, now + 0.12); // A5

      osc2.frequency.setValueAtTime(880, now + 0.12);
      osc2.frequency.exponentialRampToValueAtTime(1174.66, now + 0.25); // D6

      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(this.ctx.destination);

      osc1.start(now);
      osc2.start(now + 0.1);
      osc1.stop(now + 0.35);
      osc2.stop(now + 0.35);
    } catch (_err) {
      /* AudioContext unavailable or autoplay blocked */
    }
  }

  /**
   * Task Complete Chime (Harmonic triple pulse)
   */
  playSuccess() {
    if (!this.soundEnabled) return;
    try {
      this.initContext();
      if (!this.ctx) return;
      const now = this.ctx.currentTime;

      [523.25, 659.25, 1046.5].forEach((freq, i) => {
        if (!this.ctx) return;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, now + i * 0.08);

        gain.gain.setValueAtTime(0.07, now + i * 0.08);
        gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.08 + 0.2);

        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.start(now + i * 0.08);
        osc.stop(now + i * 0.08 + 0.2);
      });
    } catch (_err) {
      /* AudioContext unavailable or autoplay blocked */
    }
  }

  /**
   * Diagnostic / Scan Tone (Subtle high-tech data sweep)
   */
  playScan() {
    if (!this.soundEnabled) return;
    try {
      this.initContext();
      if (!this.ctx) return;
      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(400, now);
      osc.frequency.exponentialRampToValueAtTime(1200, now + 0.15);

      gain.gain.setValueAtTime(0.04, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start(now);
      osc.stop(now + 0.2);
    } catch (_err) {
      /* AudioContext unavailable or autoplay blocked */
    }
  }

  /**
   * Stark Warning / Alert Tone
   */
  playAlert() {
    if (!this.soundEnabled) return;
    try {
      this.initContext();
      if (!this.ctx) return;
      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(320, now);
      osc.frequency.setValueAtTime(280, now + 0.1);

      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start(now);
      osc.stop(now + 0.25);
    } catch (_err) {
      /* AudioContext unavailable or autoplay blocked */
    }
  }

  /**
   * Voice Speech Synthesis with Avatar Customization and Phonetic Viseme Lip-Sync
   */
  speak(
    text: string, 
    lang: 'bn' | 'en' = 'en', 
    onEnd?: () => void,
    avatarConfig?: {
      gender?: 'male' | 'female' | 'neutral';
      pitch?: number;
      rate?: number;
      accent?: 'british' | 'us' | 'bengali';
    },
    onVisemeUpdate?: (visemeEnergy: number) => void
  ) {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
      if (onEnd) onEnd();
      return;
    }

    try {
      this.stopSpeaking();

      // Clean markdown code blocks for speech
      const cleaned = text
        .replace(/```[\s\S]*?```/g, 'Code block generated.')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/[#*_~]/g, '')
        .slice(0, 320);

      const utterance = new SpeechSynthesisUtterance(cleaned);
      utterance.rate = avatarConfig?.rate ?? 1.05;
      utterance.pitch = avatarConfig?.pitch ?? 1.0;

      // Select voice based on avatar settings
      const voices = window.speechSynthesis.getVoices();
      if (lang === 'bn' || avatarConfig?.accent === 'bengali') {
        const bnVoice = voices.find(v => v.lang.includes('bn') || v.name.includes('Bangla') || v.name.includes('Bengali'));
        if (bnVoice) utterance.voice = bnVoice;
        utterance.lang = 'bn-BD';
      } else {
        const isFemale = avatarConfig?.gender === 'female';
        const isBritish = avatarConfig?.accent === 'british';

        let targetVoice: SpeechSynthesisVoice | undefined;

        if (isFemale) {
          targetVoice = voices.find(v => 
            (isBritish && (v.name.includes('UK') || v.lang.includes('GB')) && (v.name.includes('Female') || v.name.includes('Victoria') || v.name.includes('Stephanie'))) ||
            v.name.includes('Samantha') ||
            v.name.includes('Zira') ||
            v.name.includes('Karen') ||
            (v.name.includes('Female') && v.lang.includes('en'))
          );
        } else {
          // Male / Default Jarvis
          targetVoice = voices.find(v => 
            (isBritish && (v.name.includes('Daniel') || v.name.includes('UK English Male') || v.name.includes('Oliver') || v.name.includes('George'))) ||
            v.name.includes('Daniel') ||
            v.name.includes('David') ||
            v.name.includes('Alex') ||
            (v.name.includes('Male') && v.lang.includes('en'))
          );
        }

        // Fallback to any English natural voice if specific one not found
        if (!targetVoice) {
          targetVoice = voices.find(v => v.name.includes('Natural') || v.lang.includes('en'));
        }

        if (targetVoice) utterance.voice = targetVoice;
        utterance.lang = isBritish ? 'en-GB' : 'en-US';
      }

      // Viseme modulation during speech
      if (onVisemeUpdate) {
        this.visemeTimer = setInterval(() => {
          // Natural speech oscillation between 0.2 and 0.85
          const visemeEnergy = 0.25 + Math.random() * 0.65;
          onVisemeUpdate(visemeEnergy);
        }, 85);

        utterance.onboundary = (e) => {
          if (e.name === 'word') {
            // Emphasize speech onset
            onVisemeUpdate(0.75 + Math.random() * 0.25);
          }
        };
      }

      const cleanup = () => {
        if (this.visemeTimer) {
          clearInterval(this.visemeTimer);
          this.visemeTimer = null;
        }
        if (onVisemeUpdate) onVisemeUpdate(0);
        if (onEnd) onEnd();
      };

      utterance.onend = cleanup;
      utterance.onerror = cleanup;

      window.speechSynthesis.speak(utterance);
    } catch {
      if (this.visemeTimer) {
        clearInterval(this.visemeTimer);
        this.visemeTimer = null;
      }
      if (onVisemeUpdate) onVisemeUpdate(0);
      if (onEnd) onEnd();
    }
  }

  stopSpeaking() {
    if (this.visemeTimer) {
      clearInterval(this.visemeTimer);
      this.visemeTimer = null;
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }
}

export const jarvisAudio = new JarvisAudioEngine();
