import { useState } from 'react';
import { HelpCircle } from 'lucide-react';

interface BanglaHintProps {
  text: string;
}

export const BanglaHint = ({ text }: BanglaHintProps) => {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <span className="relative inline-block" onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)}>
      <button
        className="inline-flex items-center justify-center rounded-full p-1 text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors"
        aria-label="টিপস"
      >
        <HelpCircle className="w-4 h-4" />
      </button>
      {showTooltip && (
        <div
          className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-slate-900 border border-cyan-500/30 text-slate-200 text-xs rounded-md shadow-lg z-50 whitespace-nowrap tooltip-enter"
          role="tooltip"
        >
          <p className="font-bengali">{text}</p>
        </div>
      )}
    </span>
  );
};
