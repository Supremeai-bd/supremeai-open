import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../../services/apiClient';
import { useUpdateRules } from '../../data/hooks';
import { useAuthStore } from '../../../store/authStore';
import { JsonViewer, ConfirmModal, EmptyState } from '../../kit';

export function RulesPolicy() {
  // Issue #1831 fix: dead 'admin_token' localStorage gate (never written) →
  // auth-store gate, same pattern as SecretsHealth.tsx.
  const isAdminAuthenticated = useAuthStore((s) => s.role === 'admin' && s.status === 'loggedIn');
  const { data: rules, isLoading } = useQuery({
    queryKey: ['cmd', 'rules'],
    queryFn: () => apiClient.get<Record<string, unknown>>('/admin-api/rules'),
    enabled: isAdminAuthenticated,
    staleTime: 60_000,
  });
  const updateRules = useUpdateRules();
  const [showSave, setShowSave] = useState(false);
  const [otp, setOtp] = useState('');
  const [localRules, setLocalRules] = useState<Record<string, unknown> | null>(null);

  if (!rules && isLoading) {
    return <EmptyState title="রুলস লোড হচ্ছে..." message="পলিসি কনফিগ ফেচ করা হচ্ছে..." loading />;
  }

  const handleSave = () => {
    updateRules.mutate({ ...localRules, otp });
    setShowSave(false);
    setOtp('');
  };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Rules & Policy</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--sa-text-2)]">CURRENT RULES</div>
          <button
            onClick={() => { setLocalRules(rules as Record<string, unknown>); setShowSave(true); }}
            className="px-3 py-1.5 rounded-lg border border-[#00f3ff]/30 text-[#00f3ff] text-[9px] font-mono hover:bg-[#00f3ff]/10 transition-colors"
          >
            EDIT RULES (OTP)
          </button>
        </div>
        <JsonViewer data={rules ?? {}} />
      </div>
      <ConfirmModal
        open={showSave}
        title="রুলস আপডেট"
        message="নিশ্চিত করতে OTP দিন"
        onCancel={() => { setShowSave(false); setOtp(''); }}
        onConfirm={handleSave}
      />
    </div>
  );
}
