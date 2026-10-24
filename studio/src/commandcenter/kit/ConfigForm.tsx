import { useState } from 'react';
import { Eye, EyeOff, Save } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Config Form (masked)
// বাংলা মন্তব্য: এনভি ভ্যারিয়েবল এডিট — ভ্যালু masked, OTP save
// ═══════════════════════════════════════════════════════════════════════════

interface ConfigFormProps {
  entries: Array<{ key: string; value: string; masked: boolean }>;
  onSave: (key: string, value: string) => void;
  saving?: boolean;
}

export function ConfigForm({ entries, onSave, saving }: ConfigFormProps) {
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [showValue, setShowValue] = useState<Record<string, boolean>>({});

  const handleEdit = (key: string, value: string) => {
    setEditingKey(key);
    setEditValue(value);
  };

  const handleSave = (key: string) => {
    onSave(key, editValue);
    setEditingKey(null);
    setEditValue('');
  };

  return (
    <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] overflow-hidden">
      <div className="px-4 py-2 border-b border-[var(--sa-line)] flex items-center justify-between">
        <span className="text-[10px] font-mono uppercase tracking-widest text-[var(--sa-text-1)]">
          কনফিগারেশন · CONFIG
        </span>
        <span className="text-[9px] font-mono text-[var(--sa-text-2)]">{entries.length} entries</span>
      </div>
      <div className="divide-y divide-[var(--sa-line)]">
        {entries.map((entry) => (
          <div key={entry.key} className="px-4 py-2.5 flex items-center gap-3">
            <span className="text-xs font-mono text-[#00f3ff] flex-1">{entry.key}</span>
            {editingKey === entry.key ? (
              <div className="flex items-center gap-2 flex-1">
                <input
                  type={showValue[entry.key] ? 'text' : 'password'}
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  className="flex-1 px-2 py-1 rounded bg-[var(--sa-bg-2)] border border-[#00f3ff]/30 text-xs font-mono text-[var(--sa-text-0)] focus:outline-none focus:border-[#00f3ff]"
                  autoFocus
                />
                <button
                  onClick={() => setShowValue({ ...showValue, [entry.key]: !showValue[entry.key] })}
                  className="p-1 text-[var(--sa-text-1)] hover:text-[#00f3ff]"
                >
                  {showValue[entry.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
                <button
                  onClick={() => handleSave(entry.key)}
                  disabled={saving}
                  className="px-2 py-1 rounded bg-[#00f3ff]/10 text-[#00f3ff] text-xs font-mono hover:bg-[#00f3ff]/20 disabled:opacity-50"
                >
                  <Save size={14} />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 flex-1">
                <span className="text-xs font-mono text-[var(--sa-text-1)] flex-1">
                  {entry.masked ? '••••••••••••' : entry.value}
                </span>
                <button
                  onClick={() => handleEdit(entry.key, entry.value)}
                  className="px-2 py-1 rounded border border-[var(--sa-line)] text-[10px] font-mono text-[var(--sa-text-1)] hover:border-[#00f3ff]/40 hover:text-[#00f3ff]"
                >
                  EDIT
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
