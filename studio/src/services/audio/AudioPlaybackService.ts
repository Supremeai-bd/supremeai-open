// src/services/audio/AudioPlaybackService.ts
// M14 P-C: capability-detection-সহ fail-safe Web Speech playback।
// আগে: constructor-এ window.speechSynthesis অনুপস্থিত হলেই crash —
// এখন: সৎ supported=false অবস্থা + play() স্পষ্ট ব্যর্থতা (নীরব নয়)।

import { detectWebSpeechCapability } from './webSpeechCapability';

export class AudioPlaybackService {
  private synth: SpeechSynthesis | null;
  private voice: SpeechSynthesisVoice | null = null;
  private audioContext: AudioContext | null;
  private analyser: AnalyserNode | null;
  public readonly ttsSupported: boolean;

  constructor() {
    const cap = detectWebSpeechCapability();
    this.ttsSupported = cap.ttsSupported;
    this.synth = cap.ttsSupported ? window.speechSynthesis : null;

    // AudioContext used for Visualizer (also optional in odd embeddings)
    const Ctx =
      typeof window !== 'undefined'
        ? window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        : undefined;
    if (Ctx) {
      this.audioContext = new Ctx();
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
    } else {
      this.audioContext = null;
      this.analyser = null;
    }

    if (this.ttsSupported) {
      this.loadVoices();
      if (this.synth && this.synth.onvoiceschanged !== undefined) {
        this.synth.onvoiceschanged = this.loadVoices.bind(this);
      }
    }
  }

  private loadVoices() {
    if (!this.synth) return;
    const voices = this.synth.getVoices();
    // Try to find a robotic or British female voice for SupremeAI
    this.voice = voices.find(v => v.name.includes('Google UK English Female') || v.name.includes('Zira') || v.name.includes('Samantha')) || voices[0] || null;
  }

  public getAnalyser(): AnalyserNode | null {
    return this.analyser;
  }

  /**
   * Play text via the zero-cost browser speechSynthesis engine.
   * Returns false with a loud console error when the browser does not
   * support Web Speech — callers must surface the honest failure, never
   * silently pretend audio played.
   */
  public play(text: string): boolean {
    if (!this.ttsSupported || !this.synth) {
      // M14 P-C: ভাঙা-বোতাম নয় — সৎ অসমর্থন।
      console.error('[AudioPlaybackService] speechSynthesis unavailable — browser does not support Web Speech TTS.');
      return false;
    }

    if (this.synth.speaking) {
      console.warn('⚠️ [AudioPlaybackService] Already speaking, queueing...');
    }

    const utterance = new SpeechSynthesisUtterance(text);
    if (this.voice) {
      utterance.voice = this.voice;
    }

    // Cyber-Filter adjustments (Pitch & Rate) to simulate JARVIS/SupremeAI
    utterance.pitch = 0.8; // Slightly lower pitch
    utterance.rate = 1.1;  // Slightly faster

    // Note: True routing of SpeechSynthesis through Web Audio BiquadFilterNode
    // is limited by browser security/APIs. We simulate the visualizer via a dummy oscillator
    // while the speech is active to drive the WaveformVisualizer UI.

    let osc: OscillatorNode | null = null;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    utterance.onstart = () => {
      console.warn('🗣️ [AudioPlaybackService] SupremeAI started speaking.');
      if (!this.audioContext || !this.analyser) return;
      // Create a dummy oscillator to feed the analyser so the visualizer moves
      if (this.audioContext.state === 'suspended') {
        this.audioContext.resume();
      }
      osc = this.audioContext.createOscillator();
      const gain = this.audioContext.createGain();
      gain.gain.value = 0; // Silent oscillator, only used for data

      // Modulate oscillator frequency to make the waveform look like speech
      intervalId = setInterval(() => {
        if (osc) osc.frequency.value = 100 + Math.random() * 400;
      }, 50);

      osc.connect(gain);
      gain.connect(this.analyser);
      this.analyser.connect(this.audioContext.destination);
      osc.start();
    };

    utterance.onend = () => {
      console.warn('🛑 [AudioPlaybackService] SupremeAI finished speaking.');
      if (intervalId) clearInterval(intervalId);
      if (osc) {
        osc.stop();
        osc.disconnect();
        osc = null;
      }
    };

    this.synth.speak(utterance);
    return true;
  }
}
