import { useCallback, useEffect, useRef, useState } from 'react';

type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

interface SpeechRecognitionEventLike {
  results: {
    [index: number]: {
      [index: number]: {
        transcript: string;
      };
      isFinal?: boolean;
    };
    length: number;
  };
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: unknown) => void) | null;
  onend: (() => void) | null;
}

type SRCtor = new () => SpeechRecognitionLike;

function getSpeechRecognitionCtor(): SRCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: SRCtor;
    webkitSpeechRecognition?: SRCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// M8 (issue #1519) বাংলা: Web Speech API-র `lang` একটিমাত্র BCP-47 ট্যাগ গ্রহণ
// করে — "bn-BD, en-US" অবৈধ মান, ব্রাউজার নীরবে default locale-এ ফিরে যায়,
// ফলে বাংলা STT আসলে কখনোই চলত না। কলার এখন একটি সঠিক ট্যাগ পাঠায়
// (ChatInterface: uiLang bn → bn-BD, en → en-US); ডিফল্ট bn-BD (ওয়ার্ক-অর্ডারের
// প্রাথমিক লক্ষ্য)। lang বদলালে recognition নতুন করে তৈরি হয় (effect dep)।
export function useSmartVoice(
  onFinalTranscript?: (text: string) => void,
  opts?: { lang?: string },
) {
  const sttLang = opts?.lang ?? 'bn-BD';
  const [orbState, setOrbState] = useState<VoiceState>('idle');
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  const [micAvailable, setMicAvailable] = useState(true);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const isMutedRef = useRef(isMuted);
  useEffect(() => {
    isMutedRef.current = isMuted;
  }, [isMuted]);

  const onFinalTranscriptRef = useRef(onFinalTranscript);
  useEffect(() => {
    onFinalTranscriptRef.current = onFinalTranscript;
  }, [onFinalTranscript]);

  // Initialize Speech Recognition on client; rebuilt when sttLang changes
  useEffect(() => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setMicAvailable(false);
      return;
    }

    try {
      const recog = new Ctor();
      recog.continuous = false;
      recog.interimResults = true;
      recog.lang = sttLang;

      recog.onresult = (e: SpeechRecognitionEventLike) => {
        let interimText = '';
        let finalText = '';

        for (let i = 0; i < e.results.length; i++) {
          const item = e.results[i];
          if (item && item[0]) {
            if (item.isFinal) {
              finalText += item[0].transcript;
            } else {
              interimText += item[0].transcript;
            }
          }
        }

        const currentText = (finalText || interimText).trim();
        setTranscript(currentText);

        if (finalText.trim()) {
          onFinalTranscriptRef.current?.(finalText.trim());
          setOrbState('thinking');
        }
      };

      recog.onerror = () => {
        setIsListening(false);
        setOrbState((prev) => (prev === 'listening' ? 'idle' : prev));
      };

      recog.onend = () => {
        setIsListening(false);
        setOrbState((prev) => (prev === 'listening' ? 'idle' : prev));
      };

      recognitionRef.current = recog;
    } catch {
      setMicAvailable(false);
    }

    return () => {
      try {
        recognitionRef.current?.abort();
      } catch {
        /* noop */
      }
    };
  }, [sttLang]);

  const startListening = useCallback(() => {
    if (!recognitionRef.current || isListening) return;
    try {
      // Cancel any ongoing speech synthesis first
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      setIsSpeaking(false);
      setTranscript('');
      setOrbState('listening');
      setIsListening(true);
      recognitionRef.current.start();
    } catch {
      setIsListening(false);
      setOrbState('idle');
    }
  }, [isListening]);

  const stopListening = useCallback(() => {
    if (!recognitionRef.current || !isListening) return;
    try {
      recognitionRef.current.stop();
    } catch {
      /* noop */
    }
    setIsListening(false);
    setOrbState('idle');
  }, [isListening]);

  const toggleListening = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  // Clean conversational text-to-speech using browser synthesis
  const speak = useCallback((text: string, onEnd?: () => void) => {
    if (isMutedRef.current || typeof window === 'undefined' || !window.speechSynthesis) {
      onEnd?.();
      return;
    }

    try {
      window.speechSynthesis.cancel();

      // Clean markdown, symbols, and brackets before reading aloud
      const cleanText = text
        .replace(/[*#`_~[\]()<>]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();

      if (!cleanText) {
        onEnd?.();
        return;
      }

      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = 1.05;
      utterance.pitch = 0.95; // Slightly deeper, classic British JARVIS tone

      // Select best matching voice
      const voices = window.speechSynthesis.getVoices();
      const preferredVoice = voices.find(
        (v) =>
          v.lang.startsWith('en-GB') ||
          v.name.includes('Ryan') ||
          v.name.includes('Daniel') ||
          v.name.includes('UK English') ||
          v.name.includes('Natural')
      ) || voices.find((v) => v.lang.startsWith('en')) || voices[0];

      if (preferredVoice) {
        utterance.voice = preferredVoice;
      }

      utterance.onstart = () => {
        setIsSpeaking(true);
        setOrbState('speaking');
      };

      utterance.onend = () => {
        setIsSpeaking(false);
        setOrbState('idle');
        onEnd?.();
      };

      utterance.onerror = () => {
        setIsSpeaking(false);
        setOrbState('idle');
        onEnd?.();
      };

      window.speechSynthesis.speak(utterance);
    } catch {
      setIsSpeaking(false);
      setOrbState('idle');
      onEnd?.();
    }
  }, []);

  const stopSpeaking = useCallback(() => {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    setOrbState('idle');
  }, []);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      if (next && typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel();
        setIsSpeaking(false);
        setOrbState('idle');
      }
      return next;
    });
  }, []);

  return {
    orbState,
    setOrbState,
    isListening,
    isSpeaking,
    transcript,
    isMuted,
    micAvailable,
    startListening,
    stopListening,
    toggleListening,
    speak,
    stopSpeaking,
    toggleMute,
  };
}
