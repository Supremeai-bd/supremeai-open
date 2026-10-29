import React, { useState, useEffect } from 'react';
import { 
  Key, ShieldCheck, Sliders, X, Check, Lock, Cpu, Sparkles, 
  User, Volume2, Play, Flame, Disc, Radio, Wand2, Compass,
  Upload, Image as ImageIcon, Heart, Trash2
} from 'lucide-react';
import { jarvisAudio } from '../../utils/audioFx';
import { 
  DEFAULT_AVATAR_SETTINGS, 
  AVATAR_PERSONAS, 
  type AvatarSettings,
  type AvatarPersonaId, 
  type VoiceGender, 
  type VoiceAccent, 
  type CompanionTemperament,
  type HologramMode 
} from '../../types/avatar';

interface WorkspaceSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  language: 'bn' | 'en';
  avatarSettings?: AvatarSettings;
  onSaveAvatarSettings?: (settings: AvatarSettings) => void;
}

export const WorkspaceSettingsModal: React.FC<WorkspaceSettingsModalProps> = ({
  isOpen,
  onClose,
  language,
  avatarSettings: initialAvatarSettings,
  onSaveAvatarSettings,
}) => {
  const [activeTab, setActiveTab] = useState<'avatar' | 'byok' | 'system_prompt' | 'modules'>('avatar');

  // Avatar Freedom State
  const [avatar, setAvatar] = useState<AvatarSettings>(() => {
    if (initialAvatarSettings) return initialAvatarSettings;
    try {
      const saved = localStorage.getItem('supremeai_avatar_settings');
      if (saved) return JSON.parse(saved);
    } catch (_err) {
      /* ignore invalid JSON in storage */
    }
    return DEFAULT_AVATAR_SETTINGS;
  });

  // BYOK API Keys State
  const [keys, setKeys] = useState({
    geminiKey: '•••••••••••••••••••••••••••••AIzaSy',
    openAiKey: '',
    anthropicKey: '',
    groqKey: '',
  });

  // System Prompt Overrides
  const [systemPrompt, setSystemPrompt] = useState(
    'Always generate production-ready TypeScript with strict null checks, deep space glassmorphism aesthetics, Tailwind CSS v4, and zero-pill metadata discipline.'
  );

  // Preferred Reasoning Model
  const [preferredModel, setPreferredModel] = useState('gemini-2.5-pro');

  // Feature Toggles (Module Control Center)
  const [modules, setModules] = useState({
    deepResearch: true,
    cronScheduler: true,
    mcpFederation: true,
    runtimeDevTools: true,
    humanEyeAudit: true,
  });

  const [savedSuccess, setSavedSuccess] = useState(false);
  const [isTestingVoice, setIsTestingVoice] = useState(false);

  useEffect(() => {
    if (initialAvatarSettings) {
      setAvatar(initialAvatarSettings);
    }
  }, [initialAvatarSettings]);

  if (!isOpen) return null;

  const handleSelectPersona = (id: AvatarPersonaId) => {
    const persona = AVATAR_PERSONAS.find(p => p.id === id);
    if (!persona) return;
    setAvatar(prev => ({
      ...prev,
      personaId: id,
      name: language === 'bn' ? persona.nameBn : persona.nameEn,
      gender: persona.defaultGender,
      pitch: persona.defaultPitch,
      rate: persona.defaultRate,
      accent: persona.defaultAccent,
      hologramMode: id === 'custom-companion' ? 'living_human' : prev.hologramMode,
    }));
    jarvisAudio.playScan();
  };

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const dataUrl = event.target?.result as string;
      setAvatar(prev => ({
        ...prev,
        personaId: 'custom-companion',
        customPhotoUrl: dataUrl,
        customPhotoName: file.name,
        hologramMode: 'living_human',
        relationshipArchetype: prev.relationshipArchetype || (language === 'bn' ? 'মা (Mother)' : 'Mother'),
      }));
      jarvisAudio.playActivate();
    };
    reader.readAsDataURL(file);
  };

  const handleRemovePhoto = () => {
    setAvatar(prev => ({
      ...prev,
      customPhotoUrl: undefined,
      customPhotoName: undefined,
      personaId: 'cybernetic-android',
      hologramMode: 'cyber',
    }));
  };

  const handleTestVoice = () => {
    setIsTestingVoice(true);
    jarvisAudio.playActivate();
    const testPhrase = language === 'bn'
      ? (avatar.relationshipArchetype 
          ? `নমস্কার! আমি আপনার ${avatar.relationshipArchetype}। আমি সবসময় আপনার পাশে আছি এবং আপনাকে সাহায্য করতে প্রস্তুত।`
          : `নমস্কার! আমি ${avatar.name}। আপনার এআই কোডিং সহকারী হিসেবে সর্বদা প্রস্তুত।`)
      : `Greetings. I am ${avatar.name}. All cognitive and architectural systems online.`;

    jarvisAudio.speak(
      testPhrase,
      language,
      () => setIsTestingVoice(false),
      {
        gender: avatar.gender,
        pitch: avatar.pitch,
        rate: avatar.rate,
        accent: avatar.accent,
      }
    );
  };

  const handleSave = () => {
    try {
      localStorage.setItem('supremeai_avatar_settings', JSON.stringify(avatar));
    } catch (_err) {
      /* ignore storage quota/security error */
    }

    if (onSaveAvatarSettings) {
      onSaveAvatarSettings(avatar);
    }

    jarvisAudio.playSuccess();
    setSavedSuccess(true);
    setTimeout(() => {
      setSavedSuccess(false);
      onClose();
    }, 700);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-2xl bg-slate-900 border border-white/[0.12] rounded-3xl p-6 sm:p-7 space-y-5 shadow-2xl relative text-xs font-sans max-h-[90vh] overflow-y-auto">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Modal Header */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-indigo-400 font-semibold">
            <Sliders className="w-4 h-4" />
            <span>TIER 4 WORKSPACE & AUTONOMY SETTINGS</span>
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            {language === 'bn' ? 'ব্যক্তিগত সেটিংস ও প্রিয় মানুষ হলোগ্রাম' : 'Avatar Freedom, BYOK & Studio Modules'}
          </h2>
          <p className="text-xs text-slate-400">
            {language === 'bn'
              ? 'আপনার প্রিয় মানুষ (মা, স্ত্রী, মেন্টর) এর ছবি আপলোড করে জীবন্ত হলোগ্রাম তৈরি করুন অথবা সাইবার রোবোটিক অবতার নির্বাচন করুন।'
              : 'Customize AI Persona identity, photo hologram companion, BYOK encryption vault, and autonomous studio engine modules.'}
          </p>
        </div>

        {/* Tabs Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1 p-1 bg-slate-950 border border-slate-800 rounded-xl text-xs font-medium">
          <button
            onClick={() => setActiveTab('avatar')}
            className={`py-1.5 px-2 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              activeTab === 'avatar' ? 'bg-indigo-600 text-white font-semibold shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <User className="w-3.5 h-3.5" />
            <span>Avatar Freedom</span>
          </button>

          <button
            onClick={() => setActiveTab('byok')}
            className={`py-1.5 px-2 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              activeTab === 'byok' ? 'bg-indigo-600 text-white font-semibold shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            <span>BYOK Vault</span>
          </button>

          <button
            onClick={() => setActiveTab('system_prompt')}
            className={`py-1.5 px-2 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              activeTab === 'system_prompt' ? 'bg-indigo-600 text-white font-semibold shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>System Prompt</span>
          </button>

          <button
            onClick={() => setActiveTab('modules')}
            className={`py-1.5 px-2 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              activeTab === 'modules' ? 'bg-indigo-600 text-white font-semibold shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Modules</span>
          </button>
        </div>

        {/* Tab 1: Avatar Freedom */}
        {activeTab === 'avatar' && (
          <div className="space-y-5 animate-fadeIn">
            {/* Custom Photo Companion Upload Area */}
            <div className="p-4 rounded-2xl bg-gradient-to-r from-rose-950/30 via-slate-950 to-indigo-950/30 border border-rose-500/30 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Heart className="w-4 h-4 text-rose-400" />
                  <span className="font-bold text-white text-xs">
                    {language === 'bn' ? 'প্রিয় মানুষের ছবি আপলোড (লিভিং হলোগ্রাম)' : 'Upload Favorite Person Photo (Living Hologram)'}
                  </span>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-900/60 text-rose-200 border border-rose-700/50">
                  {language === 'bn' ? '১০০% প্রাইভেট (ব্রাউজারে সংরক্ষিত)' : '100% Client-Side Private'}
                </span>
              </div>

              <p className="text-[11px] text-slate-300 leading-relaxed">
                {language === 'bn'
                  ? 'আপনার মা, স্ত্রী, সন্তান বা প্রিয় মেন্টরের একটি পোর্ট্রেট ছবি আপলোড করুন। এটি সরাসরি ৩ডি সাইয়ান/ভায়োলেট হলোগ্রাম রিং এবং ভয়েস লিপ-সিঙ্কের সাথে জীবন্ত হয়ে উঠবে।'
                  : 'Upload a portrait photo of your mother, partner, child, or mentor. It comes alive with glowing holographic rings and voice viseme lip-sync.'}
              </p>

              <div className="flex items-center gap-4 pt-1">
                {avatar.customPhotoUrl ? (
                  <div className="flex items-center gap-3">
                    <div className="relative w-14 h-14 rounded-full overflow-hidden border-2 border-cyan-400 shadow-lg shadow-cyan-500/30">
                      <img src={avatar.customPhotoUrl} alt="Companion" className="w-full h-full object-cover" />
                    </div>
                    <div>
                      <span className="font-semibold text-white text-xs block">
                        {avatar.customPhotoName || 'Photo Active'}
                      </span>
                      <button
                        onClick={handleRemovePhoto}
                        className="text-[11px] text-rose-400 hover:text-rose-300 flex items-center gap-1 mt-0.5"
                      >
                        <Trash2 className="w-3 h-3" />
                        <span>{language === 'bn' ? 'ছবি রিমুভ করুন' : 'Remove Photo'}</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <label className="flex items-center gap-2 px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl cursor-pointer font-semibold transition-all shadow-md shadow-rose-600/20">
                    <Upload className="w-3.5 h-3.5" />
                    <span>{language === 'bn' ? 'ছবি নির্বাচন করুন' : 'Select Photo'}</span>
                    <input type="file" accept="image/*" onChange={handlePhotoUpload} className="hidden" />
                  </label>
                )}

                {/* Relationship Archetype */}
                <div className="flex-1">
                  <label className="text-[10px] text-slate-400 block mb-1">
                    {language === 'bn' ? 'সম্পর্ক বা সম্বোধন:' : 'Relationship / Role:'}
                  </label>
                  <select
                    value={avatar.relationshipArchetype || 'Mother'}
                    onChange={(e) => setAvatar(prev => ({ ...prev, relationshipArchetype: e.target.value }))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white outline-none focus:border-rose-500"
                  >
                    <option value="মা (Mother)">মা (Mother)</option>
                    <option value="জীবনসঙ্গিনী (Wife / Partner)">জীবনসঙ্গিনী (Wife / Partner)</option>
                    <option value="জ্ঞানী মেন্টর (Mentor)">জ্ঞানী মেন্টর (Mentor)</option>
                    <option value="প্রিয় বন্ধু (Best Friend)">প্রিয় বন্ধু (Best Friend)</option>
                    <option value="গার্ডিয়ান এঞ্জেল (Guardian Angel)">গার্ডিয়ান এঞ্জেল (Guardian Angel)</option>
                    <option value="এআই চিফ অফ স্টাফ (Chief of Staff)">এআই চিফ অফ স্টাফ (Chief of Staff)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Personas Grid */}
            <div className="space-y-2">
              <label className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider block">
                {language === 'bn' ? 'অথবা স্ট্যান্ডার্ড এআই পারসোনা নির্বাচন করুন:' : 'Or Select Standard AI Persona:'}
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {AVATAR_PERSONAS.map((p) => {
                  const isSelected = avatar.personaId === p.id;
                  return (
                    <div
                      key={p.id}
                      onClick={() => handleSelectPersona(p.id)}
                      className={`p-3 rounded-2xl border transition-all cursor-pointer relative overflow-hidden flex flex-col justify-between ${
                        isSelected
                          ? 'bg-slate-900 border-indigo-500 shadow-md shadow-indigo-500/20 ring-1 ring-indigo-500'
                          : 'bg-slate-950/70 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-3 h-3 rounded-full shrink-0 shadow-sm"
                            style={{ backgroundColor: p.primaryColor, boxShadow: `0 0 8px ${p.primaryColor}` }}
                          />
                          <span className="font-bold text-white text-xs">
                            {language === 'bn' ? p.nameBn : p.nameEn}
                          </span>
                        </div>
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                          {p.badge}
                        </span>
                      </div>

                      <p className="text-[11px] text-slate-400 leading-snug">
                        {language === 'bn' ? p.descriptionBn : p.descriptionEn}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Hologram Engine Mode Toggle */}
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-2xl flex items-center justify-between">
              <div>
                <span className="font-semibold text-white text-xs block">
                  {language === 'bn' ? 'হলোগ্রাম ইঞ্জিন মোড' : 'Hologram Engine Mode'}
                </span>
                <span className="text-[11px] text-slate-400">
                  {avatar.hologramMode === 'living_human'
                    ? (language === 'bn' ? 'বায়োলজিক্যাল লিভিং হিউম্যান ও ফটো মোড সক্রিয়' : 'Biological Living Human & Photo Mode Active')
                    : (language === 'bn' ? 'সাইবার ৩ডি ওয়্যারফ্রেম মেস সক্রিয়' : 'Cyber 3D Wireframe Mesh Active')}
                </span>
              </div>
              <button
                onClick={() => setAvatar(prev => ({ ...prev, hologramMode: prev.hologramMode === 'living_human' ? 'cyber' : 'living_human' }))}
                className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-700 rounded-xl text-xs font-semibold text-cyan-300 transition-colors"
              >
                {avatar.hologramMode === 'living_human' ? 'Switch to Cyber 3D' : 'Switch to Living Human'}
              </button>
            </div>

            {/* Voice Timbre & Audio Controls */}
            <div className="p-4 bg-slate-950 border border-slate-800 rounded-2xl space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider">
                  {language === 'bn' ? 'ভয়েস সিন্থেসিস ও অ্যাকসেন্ট:' : 'Voice Timbre & Accent:'}
                </span>

                <button
                  onClick={handleTestVoice}
                  disabled={isTestingVoice}
                  className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg flex items-center gap-1.5 font-semibold transition-all"
                >
                  <Play className="w-3 h-3" />
                  <span>{isTestingVoice ? 'Speaking...' : (language === 'bn' ? 'ভয়েস টেস্ট' : 'Test Voice')}</span>
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">
                    {language === 'bn' ? 'ভয়েস জেন্ডার:' : 'Gender:'}
                  </label>
                  <select
                    value={avatar.gender}
                    onChange={(e) => setAvatar(prev => ({ ...prev, gender: e.target.value as VoiceGender }))}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white outline-none"
                  >
                    <option value="male">Male (পুরুষ কণ্ঠ)</option>
                    <option value="female">Female (নারী কণ্ঠ)</option>
                    <option value="neutral">Neutral (সিন্থেটিক)</option>
                  </select>
                </div>

                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">
                    {language === 'bn' ? 'অ্যাকসেন্ট:' : 'Accent:'}
                  </label>
                  <select
                    value={avatar.accent}
                    onChange={(e) => setAvatar(prev => ({ ...prev, accent: e.target.value as VoiceAccent }))}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white outline-none"
                  >
                    <option value="british">British (Daniel / Stark)</option>
                    <option value="us">US Natural</option>
                    <option value="bengali">বাংলা (Bangla Native)</option>
                  </select>
                </div>

                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">
                    {language === 'bn' ? 'মেজাজ / টেম্পারামেন্ট:' : 'Temperament:'}
                  </label>
                  <select
                    value={avatar.temperament}
                    onChange={(e) => setAvatar(prev => ({ ...prev, temperament: e.target.value as CompanionTemperament }))}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white outline-none"
                  >
                    <option value="ironman_jarvis">Iron Man JARVIS (Canonical)</option>
                    <option value="empathetic_copilot">Empathetic Co-pilot</option>
                    <option value="architect">Senior Software Architect</option>
                    <option value="warm_mentor">Warm Loving Mentor</option>
                  </select>
                </div>
              </div>

              {/* Sliders for Pitch and Rate */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">{language === 'bn' ? 'পিচ (Pitch):' : 'Voice Pitch:'}</span>
                    <span className="font-mono text-indigo-400">{avatar.pitch.toFixed(2)}x</span>
                  </div>
                  <input
                    type="range"
                    min="0.7"
                    max="1.4"
                    step="0.05"
                    value={avatar.pitch}
                    onChange={(e) => setAvatar(prev => ({ ...prev, pitch: parseFloat(e.target.value) }))}
                    className="w-full accent-indigo-500 cursor-pointer"
                  />
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">{language === 'bn' ? 'গতি (Rate):' : 'Speech Rate:'}</span>
                    <span className="font-mono text-indigo-400">{avatar.rate.toFixed(2)}x</span>
                  </div>
                  <input
                    type="range"
                    min="0.8"
                    max="1.3"
                    step="0.05"
                    value={avatar.rate}
                    onChange={(e) => setAvatar(prev => ({ ...prev, rate: parseFloat(e.target.value) }))}
                    className="w-full accent-indigo-500 cursor-pointer"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: BYOK Vault */}
        {activeTab === 'byok' && (
          <div className="space-y-4 animate-fadeIn">
            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-3">
              <span className="font-semibold text-white text-xs block">
                {language === 'bn' ? 'API কী এনক্রিপশন ভল্ট' : 'Client-Side BYOK Encryption Vault'}
              </span>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                {language === 'bn'
                  ? 'আপনার নিজস্ব API কী ব্যবহার করুন। কীগুলি ব্রাউজারের এনক্রিপ্টেড স্যান্ডবক্সে সংরক্ষিত থাকে।'
                  : 'Keys are stored strictly in client-side encrypted local storage. Unlimited rate limits apply.'}
              </p>

              <div className="space-y-2">
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">Google Gemini API Key:</label>
                  <input
                    type="password"
                    value={keys.geminiKey}
                    onChange={(e) => setKeys(prev => ({ ...prev, geminiKey: e.target.value }))}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">OpenAI API Key (Optional):</label>
                  <input
                    type="password"
                    value={keys.openAiKey}
                    placeholder="sk-proj-..."
                    onChange={(e) => setKeys(prev => ({ ...prev, openAiKey: e.target.value }))}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 font-mono outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: System Prompt Overrides */}
        {activeTab === 'system_prompt' && (
          <div className="space-y-4 animate-fadeIn">
            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 space-y-3">
              <span className="font-semibold text-white text-xs block">
                {language === 'bn' ? 'গ্লোবাল সিস্টেম প্রম্পট গাইডলাইন' : 'Global Architectural Directives'}
              </span>
              <textarea
                rows={5}
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 font-mono leading-relaxed outline-none focus:border-indigo-500"
              />
            </div>
          </div>
        )}

        {/* Tab 4: Autonomous Modules */}
        {activeTab === 'modules' && (
          <div className="space-y-3 animate-fadeIn">
            {[
              { id: 'deepResearch', label: 'Deep Multi-Hop Research Engine', desc: 'Recursive web-search and synthesis before code generation' },
              { id: 'cronScheduler', label: 'Autonomous Cron Job Monitor', desc: 'Background health verification and server heartbeat loop' },
              { id: 'mcpFederation', label: 'MCP Tower 142 Federation Tools', desc: 'Handshake with Render MCP endpoint and tool federation' },
              { id: 'humanEyeAudit', label: 'Human-Eye Contrast & Anti-Slop Audit', desc: 'Automatic CSS compliance checks and dark-mode validation' },
            ].map((mod) => (
              <div key={mod.id} className="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-between">
                <div>
                  <span className="font-semibold text-white text-xs block">{mod.label}</span>
                  <span className="text-[10px] text-slate-400">{mod.desc}</span>
                </div>
                <input
                  type="checkbox"
                  checked={(modules as any)[mod.id]}
                  onChange={() => setModules(prev => ({ ...prev, [mod.id]: !(prev as any)[mod.id] }))}
                  className="w-4 h-4 accent-indigo-600 rounded cursor-pointer"
                />
              </div>
            ))}
          </div>
        )}

        {/* Modal Footer */}
        <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {savedSuccess && (
              <span className="text-emerald-400 text-xs flex items-center gap-1 font-semibold animate-pulse">
                <Check className="w-4 h-4" />
                <span>{language === 'bn' ? 'সেটিংস সফলভাবে সংরক্ষিত!' : 'Settings Saved Successfully!'}</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white rounded-xl transition-colors"
            >
              {language === 'bn' ? 'বাতিল' : 'Cancel'}
            </button>
            <button
              onClick={handleSave}
              className="px-5 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-all shadow-md shadow-indigo-600/30 flex items-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" />
              <span>{language === 'bn' ? 'সেভ ও প্রয়োগ করুন' : 'Save Changes'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
