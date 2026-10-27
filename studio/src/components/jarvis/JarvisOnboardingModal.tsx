import React, { useEffect, useState } from 'react';
import { 
  Sparkles, 
  Bot, 
  User, 
  Briefcase, 
  Check, 
  X, 
  HelpCircle,
  MessageSquareHeart,
  ChevronRight,
  ShieldCheck
} from 'lucide-react';
import { apiClient } from '../../services/apiClient';
import { useAuthStore } from '../../store/authStore';

export interface JarvisOnboardingData {
  preferredSalutation: string; // e.g. "Sir", "Boss", "Bhai", "Captain", "Custom"
  customSalutation?: string;
  jarvisCustomName: string; // e.g. "Jarvis", "Friday", "Shadhin", etc.
  primaryGoal: string; // e.g. "Coding & Fullstack", "Research & Deep Thinking", "Business & Marketing", "Daily Assistant"
  experienceLevel: string; // "Beginner", "Intermediate", "Pro/Expert"
  completedAt: string;
}

const STORAGE_KEY = 'supremeai_jarvis_profile';
const SURVEY_THROTTLE_DAYS = 7;

export function getStoredJarvisProfile(): JarvisOnboardingData | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveJarvisProfile(data: JarvisOnboardingData): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // Ignore storage quota
  }
}

export const JarvisOnboardingModal: React.FC = () => {
  const { user } = useAuthStore();
  const [isOpen, setIsOpen] = useState(false);
  const [step, setStep] = useState<number>(1);
  const [isSurvey, setIsSurvey] = useState(false);

  // Form State
  const [salutation, setSalutation] = useState('Sir');
  const [customSalutation, setCustomSalutation] = useState('');
  const [jarvisName, setJarvisName] = useState('JARVIS');
  const [primaryGoal, setPrimaryGoal] = useState('Coding & Autonomous Agents');
  const [experienceLevel, setExperienceLevel] = useState('Pro / Developer');
  const [surveySatisfaction, setSurveySatisfaction] = useState('5');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // Check if user has answered onboarding
    const existing = getStoredJarvisProfile();
    const lastPromptTime = localStorage.getItem('supremeai_jarvis_prompt_time');
    const now = Date.now();

    if (!existing) {
      // New user or guest: pop up after a slight delay (1.5s)
      const timer = setTimeout(() => {
        setIsSurvey(false);
        setIsOpen(true);
      }, 1500);
      return () => clearTimeout(timer);
    } else {
      // If user completed onboarding, run periodical survey (every 7 days)
      if (lastPromptTime) {
        const lastTime = parseInt(lastPromptTime, 10);
        const daysDiff = (now - lastTime) / (1000 * 60 * 60 * 24);
        if (daysDiff >= SURVEY_THROTTLE_DAYS) {
          const timer = setTimeout(() => {
            setIsSurvey(true);
            setIsOpen(true);
          }, 3500);
          return () => clearTimeout(timer);
        }
      } else {
        localStorage.setItem('supremeai_jarvis_prompt_time', now.toString());
      }
    }
  }, [user]);

  const handleSave = async () => {
    setSaving(true);
    const finalSalutation = salutation === 'Custom' && customSalutation.trim() ? customSalutation.trim() : salutation;
    const finalName = jarvisName.trim() || 'JARVIS';

    const profileData: JarvisOnboardingData = {
      preferredSalutation: finalSalutation,
      customSalutation: customSalutation.trim(),
      jarvisCustomName: finalName,
      primaryGoal,
      experienceLevel,
      completedAt: new Date().toISOString(),
    };

    saveJarvisProfile(profileData);
    localStorage.setItem('supremeai_jarvis_prompt_time', Date.now().toString());

    // Sync with backend preferences if logged in
    try {
      if (user) {
        await apiClient.post('/api/preferences/', {
          profile: {
            salutation: finalSalutation,
            assistant_name: finalName,
            primary_goal: primaryGoal,
            experience_level: experienceLevel,
            survey_rating: surveySatisfaction,
          },
        });
      }
    } catch {
      // Local fallback preserves choice
    } finally {
      setSaving(false);
      setIsOpen(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-300">
      <div className="relative w-full max-w-lg rounded-3xl border border-cyan-500/30 bg-gradient-to-b from-slate-900 via-slate-950 to-slate-950 p-6 sm:p-8 shadow-2xl shadow-cyan-950/50">
        
        {/* Glow decoration */}
        <div className="absolute top-0 right-1/4 -mt-10 w-48 h-48 bg-cyan-500/20 rounded-full blur-3xl pointer-events-none" />

        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-white/10 pb-5">
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Bot className="w-6 h-6 animate-pulse" />
              <div className="absolute -top-1 -right-1 w-3 h-3 bg-cyan-400 rounded-full animate-ping" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs uppercase font-mono tracking-widest text-cyan-400 font-semibold">
                  {jarvisName} Neural Setup
                </span>
                <span className="px-2 py-0.5 rounded-full text-[10px] bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                  {isSurvey ? 'Periodic Survey' : `Step ${step} of 3`}
                </span>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                {isSurvey 
                  ? `Hey, it's ${jarvisName}! Quick Check-in` 
                  : `Welcome! Let's personalize your ${jarvisName}`}
              </h2>
            </div>
          </div>

          <button
            onClick={() => setIsOpen(false)}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
            title="Dismiss for now"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="py-6 space-y-5">
          {isSurvey ? (
            /* 📋 PERIODIC SURVEY INTERACTION */
            <div className="space-y-4">
              <p className="text-xs text-slate-300 leading-relaxed">
                আমি আপনার SupremeAI অভিজ্ঞতা আরও উন্নত করতে চাই। আপনার কেমন লাগছে এবং আমি কি আপনার প্রত্যাশা পূরণ করতে পারছি?
              </p>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-2">
                  Overall System & AI Experience (1 - 5):
                </label>
                <div className="grid grid-cols-5 gap-2">
                  {[
                    { val: '1', label: '😞 Poor' },
                    { val: '2', label: '😐 Okay' },
                    { val: '3', label: '🙂 Good' },
                    { val: '4', label: '🚀 Great' },
                    { val: '5', label: '🔥 Perfect' },
                  ].map((item) => (
                    <button
                      key={item.val}
                      type="button"
                      onClick={() => setSurveySatisfaction(item.val)}
                      className={`p-2 rounded-xl text-center border text-xs font-medium transition ${
                        surveySatisfaction === item.val
                          ? 'border-cyan-400 bg-cyan-500/20 text-white shadow-sm shadow-cyan-500/30'
                          : 'border-white/10 bg-white/[0.02] text-slate-400 hover:bg-white/[0.05]'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Would you like me to adapt my communication tone or name?
                </label>
                <input
                  type="text"
                  value={jarvisName}
                  onChange={(e) => setJarvisName(e.target.value)}
                  placeholder="Assistant name (default: JARVIS)"
                  className="w-full px-3 py-2 text-xs rounded-xl bg-black/40 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
                />
              </div>
            </div>
          ) : (
            /* 🚀 INITIAL ONBOARDING STEPS */
            <>
              {step === 1 && (
                <div className="space-y-4 animate-in fade-in duration-200">
                  <div className="space-y-1">
                    <label className="block text-xs font-semibold text-slate-200">
                      ১. আমি আপনাকে কীভাবে সম্বোধন করব? (Salutation)
                    </label>
                    <p className="text-[11px] text-slate-400">
                      JARVIS আপনার সাথে কথা বলার সময় এই সম্বোধন ব্যবহার করবে।
                    </p>
                  </div>

                  <div className="grid grid-cols-3 gap-2.5">
                    {['Sir', 'Boss', 'Captain', 'Bhai', 'Chief', 'Custom'].map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => setSalutation(item)}
                        className={`p-2.5 rounded-xl text-xs font-semibold border transition ${
                          salutation === item
                            ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200 shadow-md shadow-cyan-500/20'
                            : 'border-white/10 bg-white/[0.02] text-slate-400 hover:bg-white/[0.06] hover:text-white'
                        }`}
                      >
                        {item}
                      </button>
                    ))}
                  </div>

                  {salutation === 'Custom' && (
                    <input
                      type="text"
                      value={customSalutation}
                      onChange={(e) => setCustomSalutation(e.target.value)}
                      placeholder="আপনার পছন্দমত নাম বা পদবি লিখুন (উদাঃ ওস্তাদ, ফ্রেন্ড)..."
                      className="w-full px-3 py-2 text-xs rounded-xl bg-black/40 border border-cyan-500/40 text-white placeholder-slate-500 focus:outline-none"
                    />
                  )}
                </div>
              )}

              {step === 2 && (
                <div className="space-y-4 animate-in fade-in duration-200">
                  <div className="space-y-1">
                    <label className="block text-xs font-semibold text-slate-200">
                      ২. আমার নাম পরিবর্তন করতে চান কি? (AI Persona Name)
                    </label>
                    <p className="text-[11px] text-slate-400">
                      ডিফল্ট নাম &quot;JARVIS&quot;। আপনি চাইলে যেকোনো পছন্দসই নাম দিতে পারেন।
                    </p>
                  </div>

                  <div className="relative">
                    <input
                      type="text"
                      value={jarvisName}
                      onChange={(e) => setJarvisName(e.target.value)}
                      placeholder="JARVIS"
                      className="w-full px-4 py-2.5 text-sm rounded-xl bg-black/40 border border-white/10 text-white placeholder-slate-500 font-mono focus:outline-none focus:border-cyan-500/60"
                    />
                    <Sparkles className="absolute right-3 top-3 w-4 h-4 text-cyan-400" />
                  </div>

                  <div className="flex gap-2">
                    {['JARVIS', 'FRIDAY', 'SHADHIN', 'NEXUS'].map((name) => (
                      <button
                        key={name}
                        type="button"
                        onClick={() => setJarvisName(name)}
                        className="px-2.5 py-1 text-[11px] rounded-lg bg-white/[0.03] hover:bg-white/10 text-slate-300 border border-white/5 transition"
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-4 animate-in fade-in duration-200">
                  <div className="space-y-1">
                    <label className="block text-xs font-semibold text-slate-200">
                      ৩. আমাদের সিস্টেম মূলত কোন কাজে ব্যবহার করতে চান?
                    </label>
                    <p className="text-[11px] text-slate-400">
                      আপনার কাজের ধরন অনুসারে মডেল ও টুলস অপটিমাইজ করা হবে।
                    </p>
                  </div>

                  <div className="space-y-2">
                    {[
                      { title: 'Coding & Autonomous Agents', desc: 'Fullstack, Python, Bug Fixing & Git Automations' },
                      { title: 'Deep Research & Learning', desc: 'Complex problem analysis, synthesis & papers' },
                      { title: 'Business, Content & Operations', desc: 'Marketing, social growth, copy and workflows' },
                      { title: 'Daily Intelligent Assistant', desc: 'Tasks, fast Q&A, voice guidance & brainstorming' },
                    ].map((item) => (
                      <div
                        key={item.title}
                        onClick={() => setPrimaryGoal(item.title)}
                        className={`p-3 rounded-xl border cursor-pointer transition flex items-center justify-between ${
                          primaryGoal === item.title
                            ? 'border-cyan-400 bg-cyan-500/15 text-white'
                            : 'border-white/10 bg-white/[0.02] text-slate-400 hover:bg-white/[0.05]'
                        }`}
                      >
                        <div>
                          <p className="text-xs font-semibold text-slate-200">{item.title}</p>
                          <p className="text-[10px] text-slate-400">{item.desc}</p>
                        </div>
                        {primaryGoal === item.title && (
                          <Check className="w-4 h-4 text-cyan-400" />
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Controls */}
        <div className="flex items-center justify-between pt-4 border-t border-white/10">
          {!isSurvey && step > 1 ? (
            <button
              type="button"
              onClick={() => setStep((s) => s - 1)}
              className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white transition"
            >
              Back
            </button>
          ) : (
            <span className="text-[11px] text-slate-500 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-500/70" />
              <span>Zero-admin synced</span>
            </span>
          )}

          <div className="flex items-center gap-2">
            {!isSurvey && step < 3 ? (
              <button
                type="button"
                onClick={() => setStep((s) => s + 1)}
                className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-xs transition shadow-lg shadow-cyan-500/20"
              >
                <span>Continue</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-slate-950 font-semibold text-xs transition shadow-lg shadow-cyan-500/30"
              >
                {saving ? (
                  <span>Saving...</span>
                ) : (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    <span>{isSurvey ? 'Submit Check-in' : 'Finish & Activate'}</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};

export default JarvisOnboardingModal;
