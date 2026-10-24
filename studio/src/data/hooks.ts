import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import type { ApprovalDecision, ApprovalItem, ApprovalListResponse, ApprovalMutationResult } from '../types/approval';

const approvalKey = ['admin', 'approvals'] as const;

async function listApprovals(): Promise<ApprovalItem[]> {
  const response = await apiClient.get<ApprovalListResponse | ApprovalItem[]>('/api/v1/hitl/pending');
  return Array.isArray(response) ? response : response.items ?? [];
}

export function useApprovalQueue() {
  return useQuery({
    queryKey: approvalKey,
    queryFn: listApprovals,
    refetchInterval: 15000,
    staleTime: 5000,
  });
}

export function useApprovalDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (decision: ApprovalDecision) => {
      const action = decision.action ?? (decision.approve ? 'approve' : 'reject');
      if (action === 'approve') {
        return apiClient.post<ApprovalMutationResult>(`/api/v1/hitl/approve/${decision.id}`, { otp: decision.otp ?? '' });
      }
      if (action === 'reject') {
        return apiClient.post<ApprovalMutationResult>(`/api/v1/hitl/reject/${decision.id}`, { reason: decision.reason ?? '' });
      }
      return apiClient.post<ApprovalMutationResult>(`/api/v1/hitl/cancel/${decision.id}`, { reason: decision.reason ?? '' });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: approvalKey }),
  });
}

export const useApproveAction = useApprovalDecision;
