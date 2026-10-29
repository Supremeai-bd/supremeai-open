import React, { useState } from 'react';
import { Wrench, Palette, Briefcase, Sparkles, X, Check, SlidersHorizontal, ArrowRight } from 'lucide-react';
import { jarvisAudio } from '../../utils/audioFx';

export type UserPersona = 'developer' | 'designer' | 'founder' | 'default';

interface IntentDiscoveryBannerProps {
  currentPersona: UserPersona;
  onSelectPersona: (persona: UserPersona) => void;
  onOpenSettings?: () => void;
  language: 'bn' | 'en';
}

export const IntentDiscoveryBanner: React.FC<IntentDiscoveryBannerProps> = ({
  currentPersona,
  onSelectPersona,
  onOpenSettings,
  language,
}) => {
  const [isDismissed, setIsDismissed] = useState(false);

  if (isDismissed) return null;

  const personas = [
    {
      id: 'developer' as UserPersona,
      titleBn: '🛠️ ফুল-স্ট্যাক ডেভেলপার / ইঞ্জিনিয়ার',
      titleEn: '🛠️ Full-Stack Developer',
      descBn: 'কোড ডিভ, র টার্মিনাল, গিট ব্রাঞ্চ ও MCP সার্ভার কনফিগারেশন প্রায়োরিটাইজ করুন',
      descEn: 'Prioritizes raw Monaco editor, Git diffs, terminal, & live MCP server federation',
      color: 'hover:border-indigo-500/60',
      activeColor: 'bg-indigo-950/80 border-indigo-500 text-white',
    },
    {
      id: 'designer' as UserPersona,
      titleBn: '🎨 ডিজাইনার / প্রোডাক্ট ক্রিয়েটর',
      titleEn: '🎨 Designer & Creator',
      descBn: 'ভিজ্যুয়াল ক্লিক-টু-এডিট, রেসপন্সিভ ক্যানভাস ও টেলউইন্ড/সিএসএস টিউনিং',
      descEn: 'Prioritizes Click-to-Edit visual inspector, 3-device canvas & optical contrast',
      color: 'hover:border-purple-500/60',
      activeColor: 'bg-purple-950/80 border-purple-500 text-white',
    },
    {
      id: 'founder' as UserPersona,
      titleBn: '📊 ফাউন্ডার / ডোমেন স্পেশালিস্ট',
      titleEn: '📊 Founder / Product PM',
      descBn: 'ন্যাচারাল ল্যাঙ্গুয়েজ প্রম্পট, ইনস্ট্যান্ট এমভিপি জেনারেশন ও ১-ক্লিক ক্লাউড পাবলিশ',
      descEn: 'Prioritizes autonomous agent flow, instant MVP synthesis, & 1-click cloud live hosting',
      color: 'hover:border-emerald-500/60',
      activeColor: 'bg-emerald-950/80 border-emerald-500 text-white',
    },
  ];

  const handleSelect = (p: UserPersona) => {
    jarvisAudio.playActivate();
    onSelectPersona(p);
  };

  return (
    <div className="relative bg-gradient-to-r from-slate-900/90 via-slate-950 to-slate-900/90 border border-indigo-500/30 rounded-2xl p-4 sm:p-5 shadow-2xl backdrop-blur-md mb-4 text-xs font-sans transition-all">
      {/* Close button */}
      <button
        onClick={() => setIsDismissed(true)}
        className="absolute top-3.5 right-3.5 text-slate-500 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
        title="Dismiss discovery banner"
      >
        <X className="w-3.5 h-3.5" />
      </button>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-300">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <h3 className="font-bold text-white text-sm tracking-tight flex items-center gap-2">
              <span>{language === 'bn' ? 'অ্যাডাপ্টিভ ইন্টেন্ট ডিসকভারি (Tier 2 Engine)' : 'Adaptive Intent Discovery (Tier 2 Engine)'}</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800">
                Auto-Tuned Cockpit
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              {language === 'bn'
                ? 'আপনার কাজের ধরন অনুযায়ী স্টুডিওর টুলস, প্যানেল ডেনসিটি ও শর্টকাট স্বয়ংক্রিয়ভাবে টিউন হবে।'
                : 'Customizes panel layout, default tool density, and autonomous personas according to your role.'}
            </p>
          </div>
        </div>

        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="self-start md:self-auto flex items-center gap-1.5 px-3 py-1 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white rounded-lg border border-slate-800 transition-colors text-[11px] font-mono"
          >
            <SlidersHorizontal className="w-3 h-3 text-indigo-400" />
            <span>{language === 'bn' ? 'কাস্টম সেটিংস' : 'BYOK & Settings'}</span>
          </button>
        )}
      </div>

      {/* 3 Persona Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 pt-3">
        {personas.map((p) => {
          const isSelected = currentPersona === p.id;
          return (
            <div
              key={p.id}
              onClick={() => handleSelect(p.id)}
              className={`p-3 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${p.color} ${
                isSelected
                  ? p.activeColor + ' shadow-lg'
                  : 'bg-slate-950/70 border-slate-800/80 text-slate-300 hover:bg-slate-900/60'
              }`}
            >
              <div>
                <div className="flex items-center justify-between font-bold text-xs mb-1">
                  <span className="text-white">{language === 'bn' ? p.titleBn : p.titleEn}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-emerald-400" />}
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  {language === 'bn' ? p.descBn : p.descEn}
                </p>
              </div>

              <div className="pt-2 text-[10px] font-mono flex items-center justify-between text-slate-500">
                <span>{isSelected ? '✓ Active Role' : 'Click to Switch'}</span>
                <ArrowRight className="w-3 h-3 opacity-60" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
