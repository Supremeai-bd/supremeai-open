export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled' | 'executed' | 'failed';

export interface ApprovalItem {
  id: string;
  action: string;
  target?: string;
  requested_by?: string;
  requested_at?: string;
  reason?: string;
  status: ApprovalStatus;
  risk_level?: string;
  expires_at?: string;
  execution_id?: string;
  execution_status?: string;
  execution_started_at?: string;
  execution_finished_at?: string;
  execution_error?: string;
}

export interface ApprovalDecision {
  id: string;
  approve?: boolean;
  action?: 'approve' | 'reject' | 'cancel';
  reason?: string;
  otp?: string;
}

export interface ApprovalMutationResult {
  success: boolean;
  status?: string;
  message?: string;
  execution_status?: string;
  error_code?: string;
}

export interface ApprovalListResponse {
  items: ApprovalItem[];
  total: number;
}
