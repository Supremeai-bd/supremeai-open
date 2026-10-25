/**
 * MobilePreviewPanel — floating overlay panel for device preview (#4148).
 *
 * বাংলা: এটি একটি floating overlay — UnifiedAppShell-এর উপরে বসে।
 * WorkspaceLayout-কে modify না করেই মোবাইল প্রিভিউ দেখায়।
 *
 * Design decisions:
 * - lucide-react icons (NOT react-icons/fi — codebase convention)
 * - cyan/neutral colors (NOT indigo — AGENTS.md prohibits indigo/blue)
 * - Uses existing BrowserPreview for iframe rendering (not parallel system)
 * - Ctrl+M keyboard shortcut (via useMobilePreview hook)
 * - Extends devicePresets.ts (8 devices + custom, not 12)
 */

import { useEffect, useRef, useState } from 'react';
import { Smartphone, X, RotateCcw, ExternalLink, Monitor } from 'lucide-react';
import { useMobilePreview } from '../../hooks/useMobilePreview';
import { DEVICE_PRESETS, getPresetById } from '../../lib/devicePresets';

export function MobilePreviewPanel({ url }: { url: string }) {
  const {
    isOpen,
    deviceId,
    orientation,
    customWidth,
    customHeight,
    toggle,
    setDevice,
    setOrientation,
    toggleOrientation,
    setCustomDimensions,
  } = useMobilePreview();

  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  // বাগ-ফিক্স: আগে ResizeObserver শুধু observe করত, callback ফাঁকা — ছোট ভিউপোর্টে
  // ডিভাইস-ফ্রেম কেটে যেত (overflow-hidden, scale নেই)। এখন আসল auto-scale:
  // ফ্রেম+বর্ডার যেন স্টেজের ভেতরে পুরো ফিট কে, সেই অনুযায়ী transform scale।
  const [scale, setScale] = useState(1);
  // বাগ-ফিক্স: স্ট্যাটাস-বারের ঘড়ি রেন্ডার-মুহূর্তের সময় দেখাত আর আর আপডেট হত না।
  // প্যানেল খোলা থাকা অবস্থায় ৩০ সেকেন্ড পরপর রিফ্রেশ (unmount-এ cleanup)।
  const [clock, setClock] = useState(() =>
    new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  );

  useEffect(() => {
    if (!isOpen) return;
    const timer = window.setInterval(() => {
      setClock(new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }));
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [isOpen]);

  // বাংলা: ডিভাইস-নির্ভর মাপগুলো pure কম্পিউটেশন — hooks-এর পরেই, early-return-এর
  // আগে হিসাব করা হয়, কারণ নিচের auto-scale effect এগুলোর উপর নির্ভরশীল।
  const currentDevice = getPresetById(deviceId) || DEVICE_PRESETS[0];
  const baseWidth = deviceId === 'custom' ? customWidth : currentDevice.width;
  const baseHeight = deviceId === 'custom' ? customHeight : currentDevice.height;
  const displayWidth = orientation === 'landscape' ? baseHeight : baseWidth;
  const displayHeight = orientation === 'landscape' ? baseWidth : baseHeight;
  // ফ্রেমের বাইরের মাপ = কনটেন্ট + বর্ডার (phone: 16px×2, tablet: 8px×2)
  const frameBorder = currentDevice.deviceType === 'tablet' ? 8 : 16;
  const outerWidth = displayWidth + frameBorder * 2;
  const outerHeight = displayHeight + frameBorder * 2;

  // বাংলা: স্টেজ (উপলব্ধ এলাকা) বনাম ফ্রেম — যেকোনো একটা ছোট হলে স্কেল < 1।
  // খোলা/ডিভাইস-পরিবর্তনের পর প্রথম পেইন্টেও সঠিক স্কেল দিতে rAF-এ মাপা হয়।
  // লক্ষ্য: Rules of Hooks — সব effect early-return-এর আগেই।
  useEffect(() => {
    if (!isOpen) return;
    const measure = () => {
      const stage = stageRef.current;
      if (!stage) return;
      const availW = stage.clientWidth - 16; // p-4 padding মাইনাস
      const availH = stage.clientHeight - 16;
      if (availW <= 0 || availH <= 0) return;
      const next = Math.min(1, availW / outerWidth, availH / outerHeight);
      setScale(Number(next.toFixed(3)));
    };
    measure();
    const raf = requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    if (stageRef.current) observer.observe(stageRef.current);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [isOpen, outerWidth, outerHeight]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-modal flex flex-col bg-black/90 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700 bg-slate-900 p-4">
        <div className="flex items-center gap-2">
          <Smartphone className="h-5 w-5 text-cyan-400" />
          <h2 className="text-lg font-semibold text-slate-100">Mobile Preview</h2>
          <span className="ml-2 text-sm text-slate-400">
            {currentDevice.name} · {displayWidth}×{displayHeight}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Device selector */}
          <select
            value={deviceId}
            onChange={(e) => setDevice(e.target.value)}
            className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
          >
            <optgroup label="📱 iPhones">
              {DEVICE_PRESETS.filter((d) => d.os === 'ios' && d.deviceType === 'phone').map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </optgroup>
            <optgroup label="🤖 Android">
              {DEVICE_PRESETS.filter((d) => d.os === 'android').map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </optgroup>
            <optgroup label="📱 Tablets">
              {DEVICE_PRESETS.filter((d) => d.deviceType === 'tablet').map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </optgroup>
            <option value="custom">⚙️ Custom</option>
          </select>

          {/* Orientation toggle */}
          <button
            onClick={toggleOrientation}
            title={`Switch to ${orientation === 'portrait' ? 'Landscape' : 'Portrait'}`}
            className="rounded border border-slate-600 bg-slate-800 p-2 text-slate-300 transition-colors hover:bg-slate-700"
          >
            <RotateCcw className="h-4 w-4" />
          </button>

          {/* বাগ-ফিক্স: আগে এখানে একটা নীরব (dead) Screenshot বাটন ছিল — onClick নেই,
              backend-এ কোনো production screenshot API নেই (browser_action_registry.py
              mock ছাড়া ৪০৪), html2canvas-ও dep নয়। মিথ্যা UI-এর বদলে বাস্তব কাজের
              বাটন: প্রিভিউ URL নতুন ট্যাবে খোলা (dependency-free, noopener-safe)। */}
          <button
            onClick={() => window.open(url, '_blank', 'noopener')}
            title="Open preview URL in new tab"
            className="rounded border border-slate-600 bg-slate-800 p-2 text-slate-300 transition-colors hover:bg-slate-700"
          >
            <ExternalLink className="h-4 w-4" />
          </button>

          {/* Close */}
          <button
            onClick={toggle}
            title="Close (Ctrl+M)"
            className="rounded border border-slate-600 bg-slate-800 p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Custom dimensions (when custom selected) */}
      {deviceId === 'custom' && (
        <div className="grid grid-cols-2 gap-3 border-b border-slate-700 bg-slate-800 p-3">
          <div>
            <label className="mb-1 block text-xs text-slate-400">Width (px)</label>
            <input
              type="number"
              value={customWidth}
              onChange={(e) => setCustomDimensions(Number(e.target.value), customHeight)}
              min={100}
              className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-slate-200 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Height (px)</label>
            <input
              type="number"
              value={customHeight}
              onChange={(e) => setCustomDimensions(customWidth, Number(e.target.value))}
              min={100}
              className="w-full rounded border border-slate-600 bg-slate-700 px-3 py-2 text-slate-200 focus:border-cyan-500 focus:outline-none"
            />
          </div>
        </div>
      )}

      {/* Device frame with iframe */}
      <div ref={stageRef} className="flex flex-1 items-center justify-center overflow-hidden bg-slate-100 p-4 dark:bg-slate-900">
        {/* বাংলা: wrapper-এ scale — ছোট ভিউপোর্টেও পুরো ডিভাইস-ফ্রেম দেখা যায়
            (কাটা পড়ে না)। scale ১ হলে আগের মতোই ১০০% সাইজ। */}
        <div
          style={{
            transform: `scale(${scale})`,
            transformOrigin: 'center center',
          }}
        >
        <div
          ref={containerRef}
          className="relative overflow-hidden bg-black shadow-2xl"
          style={{
            width: `${displayWidth}px`,
            height: `${displayHeight}px`,
            borderRadius: currentDevice.deviceType === 'tablet' ? '12px' : '25px',
            border: currentDevice.deviceType === 'tablet' ? '8px solid #e0e0e0' : '16px solid #000',
            transition: 'width 0.3s ease, height 0.3s ease',
          }}
        >
          {/* Status bar (for phones) */}
          {currentDevice.deviceType === 'phone' && currentDevice.statusBarHeight > 0 && (
            <div
              className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between bg-black px-4 text-xs text-white"
              style={{ height: `${currentDevice.statusBarHeight}px` }}
            >
              <span>{clock}</span>
              <div className="flex gap-1">
                <div className="h-2 w-4 rounded-sm bg-white" />
                <div className="h-2 w-1 rounded-sm bg-white opacity-50" />
              </div>
            </div>
          )}

          {/* Home indicator (for modern iPhones) */}
          {currentDevice.hasHomeIndicator && (
            <div className="absolute bottom-1.5 left-1/2 z-10 h-1 w-12 -translate-x-1/2 rounded-full bg-white" />
          )}

          {/* Iframe — uses same-origin URL for preview */}
          <iframe
            src={url}
            className="absolute inset-0 h-full w-full border-0"
            style={{
              top: `${currentDevice.statusBarHeight}px`,
              height: `calc(100% - ${currentDevice.statusBarHeight}px)`,
              background: 'white',
            }}
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
            title="Mobile Preview"
          />
        </div>
        </div>
      </div>

      {/* Footer with info */}
      <div className="flex items-center justify-between border-t border-slate-700 bg-slate-900 p-3 text-sm">
        <div className="flex items-center gap-2 text-slate-400">
          <Monitor className="h-4 w-4" />
          <span>Press </span>
          <kbd className="rounded bg-slate-700 px-1.5 py-0.5 text-xs">Ctrl</kbd>
          <span>+</span>
          <kbd className="rounded bg-slate-700 px-1.5 py-0.5 text-xs">M</kbd>
          <span>to toggle</span>
        </div>
        <div className="flex gap-2">
          {/* বাগ-ফিক্স: এই badge দুটি আগে span ছিল (শুধু দেখার, ক্লিক করা যেত না) —
              এখন বাটন; সরাসরি orientation সেট করে, আইকন-টগলের বদলাও। */}
          <button
            type="button"
            onClick={() => setOrientation('portrait')}
            aria-pressed={orientation === 'portrait'}
            className={`rounded px-2 py-1 text-xs transition-colors ${orientation === 'portrait' ? 'bg-cyan-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
          >
            Portrait
          </button>
          <button
            type="button"
            onClick={() => setOrientation('landscape')}
            aria-pressed={orientation === 'landscape'}
            className={`rounded px-2 py-1 text-xs transition-colors ${orientation === 'landscape' ? 'bg-green-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
          >
            Landscape
          </button>
        </div>
      </div>
    </div>
  );
}
