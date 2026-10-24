import { useState } from 'react';
import { useBackups, useCreateBackup, useRestoreBackup } from '../../data/hooks';
import { DataTable, ConfirmModal, EmptyState } from '../../kit';
import type {} from '../../data/types';

export function Backups() {
  const { data: backups, isLoading } = useBackups();
  const createBackup = useCreateBackup();
  const restoreBackup = useRestoreBackup();

  const [showCreate, setShowCreate] = useState(false);
  const [restoreId, setRestoreId] = useState<string | null>(null);
  const [otp, setOtp] = useState('');

  const handleRestore = () => {
    if (restoreId) {
      restoreBackup.mutate({ id: restoreId, otp });
      setRestoreId(null);
      setOtp('');
    }
  };

  const columns = [
    { key: 'timestamp', label: 'TIMESTAMP', width: '25%' },
    { key: 'type', label: 'TYPE', width: '15%' },
    { key: 'size_mb', label: 'SIZE', width: '10%' },
    { key: 'status', label: 'STATUS', width: '15%' },
    { key: 'retention_tag', label: 'RETENTION', width: '15%' },
  ];

  if (!backups && isLoading) {
    return <EmptyState title="ব্যাকআপ লোড হচ্ছে..." message="ব্যাকআপ লিস্ট ফেচ করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Backups</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="px-3 py-1.5 rounded-lg border border-[#10b981]/30 text-[#10b981] text-[9px] font-mono hover:bg-[#10b981]/10 transition-colors"
        >
          CREATE BACKUP
        </button>
      </div>
      <DataTable columns={columns} data={backups ?? []} rowKey={(b) => b.id} />
      <ConfirmModal
        open={showCreate}
        title="নতুন ব্যাকআপ"
        message="আপনি কি একটি নতুন ব্যাকআপ তৈরি করতে চান?"
        onCancel={() => setShowCreate(false)}
        onConfirm={() => { createBackup.mutate({}); setShowCreate(false); }}
      />
      <ConfirmModal
        open={!!restoreId}
        title="ব্যাকআপ রিস্টোর"
        message="আপনি কি এই ব্যাকআপ রিস্টোর করতে চান? OTP দিন।"
        onCancel={() => { setRestoreId(null); setOtp(''); }}
        onConfirm={handleRestore}
      />
    </div>
  );
}
