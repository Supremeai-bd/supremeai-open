import React, { useEffect, useState } from 'react';
import { X, Download } from 'lucide-react';
import QRCode from 'qrcode';

export interface QrSyncModalProps {
  open: boolean;
  url: string;
  onClose: () => void;
}

export const QrSyncModal: React.FC<QrSyncModalProps> = ({ open, url, onClose }) => {
  const [dataUrl, setDataUrl] = useState<string>('');

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    QRCode.toDataURL(url || 'https://supremeai.dev', { width: 240, margin: 2 })
      .then((u) => { if (!cancelled) setDataUrl(u); })
      .catch(() => { if (!cancelled) setDataUrl(''); });
    return () => { cancelled = true; };
  }, [open, url]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#161b22] border border-slate-700 rounded-xl p-6 w-[320px] shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white">Scan on your phone</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={16} /></button>
        </div>
        <div className="flex justify-center mb-4">
          {dataUrl ? <img src={dataUrl} alt="QR" className="rounded" /> : <div className="w-[240px] h-[240px] bg-slate-800 animate-pulse rounded" />}
        </div>
        <p className="text-xs text-slate-400 break-all mb-3">{url}</p>
        {dataUrl && (
          <a href={dataUrl} download="supremeai-qr.png" className="flex items-center justify-center gap-2 w-full py-2 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-white text-sm">
            <Download size={14} /> Download
          </a>
        )}
      </div>
    </div>
  );
};

export default QrSyncModal;