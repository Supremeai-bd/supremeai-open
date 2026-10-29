import React, { useState } from 'react';
import { Package, Check, Plus, X, Search, Sparkles } from 'lucide-react';
import { POPULAR_PACKAGES } from '../../data/projectFiles';
import type { InjectedPackage } from '../../types/worldclass';
import { jarvisAudio } from '../../utils/audioFx';

interface PackageInjectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onInjectPackage: (pkg: InjectedPackage) => void;
  language: 'bn' | 'en';
}

export const PackageInjectorModal: React.FC<PackageInjectorModalProps> = ({
  isOpen,
  onClose,
  onInjectPackage,
  language,
}) => {
  const [packages, setPackages] = useState<InjectedPackage[]>(POPULAR_PACKAGES);
  const [customPkgName, setCustomPkgName] = useState('');

  if (!isOpen) return null;

  const handleToggle = (pkg: InjectedPackage) => {
    const updated = packages.map((p) => (p.name === pkg.name ? { ...p, installed: !p.installed } : p));
    setPackages(updated);
    jarvisAudio.playActivate();
    onInjectPackage(pkg);
  };

  const handleAddCustom = () => {
    if (!customPkgName.trim()) return;
    const newPkg: InjectedPackage = {
      name: customPkgName,
      version: 'latest',
      cdnUrl: `https://cdn.jsdelivr.net/npm/${customPkgName}@latest`,
      installed: true,
      category: 'UI',
    };
    setPackages([newPkg, ...packages]);
    setCustomPkgName('');
    jarvisAudio.playSuccess();
    onInjectPackage(newPkg);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="w-full max-w-lg bg-slate-900 border border-white/[0.12] rounded-3xl p-6 sm:p-8 space-y-5 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-indigo-400 font-semibold">
            <Package className="w-4 h-4" />
            <span>INSTANT NPM / CDN PACKAGE INJECTOR</span>
          </div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            {language === 'bn' ? 'প্যাকেজ ও লাইব্রেরি ইনজেকশন' : 'Inject NPM & CDN Packages'}
          </h2>
          <p className="text-xs text-slate-400">
            {language === 'bn'
              ? 'যেকোনো থার্ড-পার্টি লাইব্রেরি (যেমন Three.js, Lucide, Confetti) সরাসরি লাইভ প্রিভিউতে ইনজেক্ট করুন।'
              : 'Add frontier visualization & UI libraries instantly into the sandboxed live renderer.'}
          </p>
        </div>

        {/* Custom Package Input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={customPkgName}
            onChange={(e) => setCustomPkgName(e.target.value)}
            placeholder="e.g. chart.js, lodash, date-fns..."
            className="flex-1 bg-slate-950 border border-slate-800 focus:border-indigo-500 rounded-xl px-3 py-2 text-xs text-slate-200 outline-none font-mono"
          />
          <button
            onClick={handleAddCustom}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl text-xs flex items-center gap-1.5 whitespace-nowrap transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Install</span>
          </button>
        </div>

        {/* Package Directory */}
        <div className="space-y-2 max-h-60 overflow-auto pr-1">
          {packages.map((pkg) => (
            <div
              key={pkg.name}
              className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-between gap-3 text-xs"
            >
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-slate-900 flex items-center justify-center text-slate-300 font-mono text-[11px] font-bold">
                  JS
                </div>
                <div>
                  <span className="font-mono font-bold text-white block">{pkg.name}</span>
                  <span className="text-[10px] text-slate-400 font-mono">v{pkg.version} · {pkg.category}</span>
                </div>
              </div>

              <button
                onClick={() => handleToggle(pkg)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold font-mono transition-colors flex items-center gap-1.5 ${
                  pkg.installed
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800 hover:bg-emerald-900'
                    : 'bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700'
                }`}
              >
                {pkg.installed ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Plus className="w-3.5 h-3.5" />}
                <span>{pkg.installed ? 'Installed' : 'Inject'}</span>
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
