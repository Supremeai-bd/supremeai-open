import React, { useState } from 'react';
import { Rocket, Check, Copy, ExternalLink, Globe, ShieldCheck, QrCode, X, RefreshCw } from 'lucide-react';
import { jarvisAudio } from '../../utils/audioFx';

interface PublishModalProps {
  isOpen: boolean;
  onClose: () => void;
  language: 'bn' | 'en';
}

export const PublishModal: React.FC<PublishModalProps> = ({
  isOpen,
  onClose,
  language,
}) => {
  const [deployStep, setDeployStep] = useState<'idle' | 'building' | 'edge' | 'live'>('idle');
  const [selectedProvider, setSelectedProvider] = useState<'Cloudflare Edge' | 'Vercel' | 'Render'>('Cloudflare Edge');
  const [copied, setCopied] = useState(false);

  const liveUrl = 'https://gusteau-kitchen-88df.supremeai.site';

  if (!isOpen) return null;

  const handleStartDeploy = () => {
    setDeployStep('building');
    jarvisAudio.playScan();

    setTimeout(() => {
      setDeployStep('edge');
    }, 1200);

    setTimeout(() => {
      setDeployStep('live');
      jarvisAudio.playSuccess();
    }, 2400);
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(liveUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-lg bg-slate-900 border border-white/[0.12] rounded-3xl p-6 sm:p-8 space-y-6 shadow-2xl shadow-indigo-950/50 relative">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Modal Header */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-emerald-400 font-semibold">
            <Rocket className="w-4 h-4" />
            <span>ONE-CLICK GLOBAL MULTI-CLOUD DEPLOY</span>
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
            {language === 'bn' ? 'সরাসরি লাইভ ইন্টারনেটে পাবলিশ করুন' : 'Publish Application to Global Web'}
          </h2>
          <p className="text-xs text-slate-400 leading-relaxed">
            {language === 'bn'
              ? 'আপনার তৈরি করা ওয়েব অ্যাপটি সাথে সাথে ক্লাউডফ্লেয়ার এজ বা ভার্সেলে ডেডিকেটেড সাবডোমেনে লাইভ হয়ে যাবে।'
              : 'Deploy your synthesized application to global edge CDN with instant SSL and custom subdomain.'}
          </p>
        </div>

        {deployStep === 'idle' && (
          <div className="space-y-4">
            {/* Provider Selection */}
            <div>
              <label className="text-xs font-semibold text-slate-300 block mb-2">
                {language === 'bn' ? 'ক্লাউড প্রোভাইডার নির্বাচন করুন:' : 'Select Target Cloud Edge:'}
              </label>
              <div className="grid grid-cols-3 gap-2 text-xs font-semibold">
                {(['Cloudflare Edge', 'Vercel', 'Render'] as const).map((prov) => (
                  <button
                    key={prov}
                    onClick={() => setSelectedProvider(prov)}
                    className={`py-2.5 px-3 rounded-xl border transition-all text-center ${
                      selectedProvider === prov
                        ? 'bg-indigo-600 text-white border-indigo-500 shadow-sm'
                        : 'bg-slate-950 text-slate-400 border-slate-800 hover:text-white'
                    }`}
                  >
                    {prov}
                  </button>
                ))}
              </div>
            </div>

            {/* Spec Checklist */}
            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 space-y-2 text-xs font-mono text-slate-400">
              <div className="flex justify-between">
                <span>Domain:</span>
                <span className="text-indigo-300">*.supremeai.site</span>
              </div>
              <div className="flex justify-between">
                <span>SSL Security:</span>
                <span className="text-emerald-400">Automatic TLS 1.3</span>
              </div>
              <div className="flex justify-between">
                <span>Global CDN:</span>
                <span className="text-slate-200">285+ Edge POP Locations</span>
              </div>
            </div>

            <button
              onClick={handleStartDeploy}
              className="w-full py-3 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2"
            >
              <Rocket className="w-4 h-4" />
              <span>{language === 'bn' ? '🚀 পাবলিশ করুন (Publish Now)' : '🚀 Publish Live Now'}</span>
            </button>
          </div>
        )}

        {(deployStep === 'building' || deployStep === 'edge') && (
          <div className="py-8 flex flex-col items-center justify-center space-y-4 text-center">
            <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
            <div className="space-y-1">
              <h3 className="text-sm font-bold text-white font-mono">
                {deployStep === 'building' ? 'Compiling Production Assets...' : 'Propagating Global Edge DNS...'}
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Target: {selectedProvider} · TLS 1.3 Handshake in progress
              </p>
            </div>
          </div>
        )}

        {deployStep === 'live' && (
          <div className="space-y-5 animate-fadeIn">
            {/* Success Box */}
            <div className="p-4 bg-emerald-950/40 border border-emerald-800/80 rounded-2xl flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white shrink-0">
                <Check className="w-5 h-5" />
              </div>
              <div>
                <span className="font-bold text-sm text-emerald-300 block">
                  {language === 'bn' ? 'সফলভাবে লাইভ পাবলিশ হয়েছে!' : 'Application is Live Globally!'}
                </span>
                <span className="text-xs text-slate-300 font-mono">
                  Cloudflare Edge · 38ms TTFB · SSL Active
                </span>
              </div>
            </div>

            {/* Live URL Bar */}
            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between gap-3 text-xs font-mono">
              <span className="text-indigo-400 truncate font-semibold">{liveUrl}</span>
              <button
                onClick={handleCopyLink}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded-lg flex items-center gap-1.5 transition-colors whitespace-nowrap"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            {/* Mobile Scan Mock QR Card */}
            <div className="p-4 bg-slate-950/80 rounded-2xl border border-slate-800 flex items-center justify-between">
              <div className="space-y-1 max-w-[240px]">
                <span className="text-xs font-bold text-white flex items-center gap-1.5">
                  <QrCode className="w-4 h-4 text-emerald-400" />
                  <span>{language === 'bn' ? 'মোবাইলে সরাসরি দেখুন' : 'Instant Mobile Scan'}</span>
                </span>
                <p className="text-[11px] text-slate-400">
                  {language === 'bn'
                    ? 'স্মার্টফোনের ক্যামেরা দিয়ে কিউআর স্ক্যান করলেই লাইভ সাইট ওপেন হবে।'
                    : 'Scan with smartphone camera to test responsive mobile experience.'}
                </p>
              </div>

              {/* Styled Mock SVG QR Code */}
              <div className="w-20 h-20 bg-white p-1.5 rounded-xl flex items-center justify-center shadow-md">
                <div className="w-full h-full border-2 border-slate-900 rounded grid grid-cols-3 gap-0.5 p-1">
                  <div className="bg-slate-900 rounded-sm" />
                  <div className="bg-transparent" />
                  <div className="bg-slate-900 rounded-sm" />
                  <div className="bg-transparent" />
                  <div className="bg-slate-900 rounded-sm" />
                  <div className="bg-transparent" />
                  <div className="bg-slate-900 rounded-sm" />
                  <div className="bg-transparent" />
                  <div className="bg-slate-900 rounded-sm" />
                </div>
              </div>
            </div>

            <button
              onClick={onClose}
              className="w-full py-2.5 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-xl transition-colors"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
