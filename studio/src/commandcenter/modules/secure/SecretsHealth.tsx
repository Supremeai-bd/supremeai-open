import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../../services/apiClient';
import { StatusPill, EmptyState } from '../../kit';
import { useAuthStore } from '../../../store/authStore';

export function SecretsHealth() {
  // SECURITY FIX: replaced localStorage.getItem('admin_token') with Zustand
  // auth store check — tokens are read by the store, never directly here.
  const isAdminAuthenticated = useAuthStore((s) => s.role === 'admin' && s.status === 'loggedIn');
  const { data: secrets, isLoading } = useQuery({
    queryKey: ['cmd', 'secrets'],
    queryFn: () => apiClient.get<{ status: string; secrets: Array<{ name: string; healthy: boolean; last_rotated?: string }> }>('/admin-api/secrets-health'),
    enabled: isAdminAuthenticated,
    staleTime: 60_000,
  });


  if (!secrets && isLoading) {
    return <EmptyState title="সিক্রেট লোড হচ্ছে..." message="সিক্রেট হেল্থ চেক করা হচ্ছে..." loading />;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-mono uppercase tracking-widest text-[var(--sa-text-2)]">Secrets Health</h2>
      <div className="rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] p-4">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-[10px] font-mono text-[var(--sa-text-2)]">OVERALL:</span>
          <StatusPill status={secrets?.status === 'healthy' ? 'healthy' : 'degraded'} label={(secrets?.status ?? 'UNKNOWN').toUpperCase()} size="md" />
        </div>
        <div className="space-y-2">
          {(secrets?.secrets ?? []).map((secret) => (
            <div key={secret.name} className="flex items-center justify-between py-2 border-b border-[var(--sa-line)] last:border-0">
              <span className="text-[10px] font-mono text-[var(--sa-text-1)]">{secret.name}</span>
              <div className="flex items-center gap-3">
                <StatusPill status={secret.healthy ? 'healthy' : 'down'} label={secret.healthy ? 'OK' : 'FAIL'} size="sm" />
                {secret.last_rotated && (
                  <span className="text-[9px] font-mono text-[var(--sa-text-3)]">rotated {secret.last_rotated}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
