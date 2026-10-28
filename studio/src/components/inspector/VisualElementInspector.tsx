import React, { useState } from 'react';
import { Sparkles, Send, X, Check, MousePointerClick, Zap, CornerDownLeft } from 'lucide-react';
import type { SelectedElementInfo } from '../../types/worldclass';

interface VisualElementInspectorProps {
  isOpen: boolean;
  onClose: () => void;
  selectedElement: SelectedElementInfo | null;
  onApplyMicroPrompt: (prompt: string, element: SelectedElementInfo) => void;
  language: 'bn' | 'en';
}

export const VisualElementInspector: React.FC<VisualElementInspectorProps> = ({
  isOpen,
  onClose,
  selectedElement,
  onApplyMicroPrompt,
  language,
}) => {
  const [microPrompt, setMicroPrompt] = useState('');
  const [isApplying, setIsApplying] = useState(false);

  if (!isOpen || !selectedElement) return null;

  const quickChips = [
    { labelBn: 'গোল্ডেন গ্র্যাডিয়েন্ট', labelEn: 'Golden Gradient', prompt: 'Make this button a luxury golden gradient with deep shadow.' },
    { labelBn: '3D গ্লাস বর্ডার', labelEn: '3D Glass Border', prompt: 'Apply 3D frosted glassmorphism with 1px translucent border and backdrop blur.' },
    { labelBn: 'প্যাডিং দ্বিগুণ করো', labelEn: 'Increase Padding', prompt: 'Increase horizontal and vertical padding by 2x for premium breathing room.' },
    { labelBn: 'পালসিং গ্লো অ্যানিমেশন', labelEn: 'Pulsing Glow', prompt: 'Add a subtle rhythmic emerald breathing glow animation.' },
  ];

  const handleSubmit = () => {
    if (!microPrompt.trim() || isApplying) return;
    setIsApplying(true);
    onApplyMicroPrompt(microPrompt, selectedElement);
    setTimeout(() => {
      setIsApplying(false);
      setMicroPrompt('');
      onClose();
    }, 600);
  };

  return (
    <div className="absolute top-16 right-6 z-50 w-80 bg-slate-900/95 backdrop-blur-xl border border-indigo-500/50 rounded-2xl shadow-2xl shadow-indigo-950/60 p-4 text-xs font-sans animate-fadeIn">
      {/* Top Header of Floating Popover */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
        <div className="flex items-center gap-1.5 font-mono text-[11px] text-indigo-400">
          <MousePointerClick className="w-3.5 h-3.5" />
          <span className="font-bold">{selectedElement.tagName.toLowerCase()}</span>
          <span className="text-slate-500 truncate max-w-[120px]">{selectedElement.selector}</span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Target Element Snippet */}
      <div className="p-2 bg-slate-950 rounded-lg border border-slate-800 text-[11px] font-mono text-slate-300 mb-3 truncate">
        {selectedElement.textContent ? `"${selectedElement.textContent.slice(0, 40)}..."` : selectedElement.className}
      </div>

      {/* Quick Modifier Chips */}
      <div className="space-y-1 mb-3">
        <span className="text-[10px] text-slate-400 font-medium block">
          {language === 'bn' ? 'কুইক অ্যাকশন প্রম্পট:' : 'Quick Actions:'}
        </span>
        <div className="flex flex-wrap gap-1">
          {quickChips.map((chip, idx) => (
            <button
              key={idx}
              onClick={() => {
                setMicroPrompt(chip.prompt);
              }}
              className="px-2 py-0.5 text-[10px] bg-slate-950 hover:bg-indigo-950/80 text-slate-300 hover:text-indigo-200 border border-slate-800 hover:border-indigo-700/60 rounded transition-colors text-left"
            >
              {language === 'bn' ? chip.labelBn : chip.labelEn}
            </button>
          ))}
        </div>
      </div>

      {/* Micro-Prompt Input */}
      <div className="space-y-2">
        <div className="relative">
          <textarea
            rows={2}
            value={microPrompt}
            onChange={(e) => setMicroPrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSubmit())}
            placeholder={
              language === 'bn'
                ? 'এই উপাদানে কী বদলাবেন? (যেমন: "বাটনটা গোল্ডেন করো")...'
                : 'How should JARVIS modify this element?...'
            }
            className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 rounded-xl p-2.5 text-xs text-slate-200 outline-none leading-relaxed placeholder-slate-500"
          />
        </div>

        <button
          onClick={handleSubmit}
          disabled={!microPrompt.trim() || isApplying}
          className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.98] text-white font-semibold rounded-xl text-xs transition-all flex items-center justify-center gap-2 shadow-md shadow-indigo-600/30 disabled:opacity-50"
        >
          {isApplying ? (
            <Sparkles className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Send className="w-3.5 h-3.5" />
          )}
          <span>{isApplying ? 'Surgically Editing...' : (language === 'bn' ? 'সরাসরি এডিট করুন' : 'Surgically Apply')}</span>
        </button>
      </div>
    </div>
  );
};
