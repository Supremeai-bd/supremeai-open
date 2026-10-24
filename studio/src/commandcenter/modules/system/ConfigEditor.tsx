import { useState } from 'react';
import { useConfigEntries, useUpdateConfig } from '../../data/hooks';
import {  ConfirmModal, EmptyState } from '../../kit';
import type {} from '../../data/types';

export function ConfigEditor() {
  const { data: config, isLoading } = useConfigEntries(120_000);
  const updateConfig = useUpdateConfig();

  const [showSave, setShowSave] = useState(false);
  const [otp, setOtp] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const handleSave = () => {
    if (selectedKey) {
      updateConfig.mutate({ key: selectedKey, value: editValue, otp });
      setShowSave(false);
      setSelectedKey(null);
      setOtp('');
    }
  };

  if (!config && isLoading) {
    return <EmptyState title="কনফিগ লোড হচ্ছে..." message="সিস্টেম কনফিগ ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Config Editor</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] overflow-hidden">
        <div className="divide-y divide-[var(--sa-line)]">
          {(config ?? []).map((entry) => (
            <div key={entry.key} className="flex items-center justify-between p-3">
              <div className="flex-1">
                <div className="text-[10px] font-mono text-[var(--sa-text-0)]">{entry.key}</div>
                <div className="text-[9px] font-mono text-[var(--sa-text-3)]">
                  {entry.masked ? 'MASKED' : entry.value}
                </div>
              </div>
              <button
                onClick={() => { setSelectedKey(entry.key); setEditValue(entry.value); setShowSave(true); }}
                className="px-2 py-1 rounded border border-[var(--sa-line)] text-[9px] font-mono text-[var(--sa-text-2)] hover:text-[var(--sa-text-0)]"
              >
                EDIT
              </button>
            </div>
          ))}
        </div>
      </div>
      <ConfirmModal
        open={showSave}
        title="কনফিগ আপডেট"
        message={`${selectedKey} আপডেট করতে OTP দিন`}
        onCancel={() => { setShowSave(false); setSelectedKey(null); setOtp(''); }}
        onConfirm={handleSave}
      />
    </div>
  );
}
