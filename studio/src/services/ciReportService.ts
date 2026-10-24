// CI/CD Report operations service for SupremeAI 2.0
// বাংলা মন্তব্য: ডাটাবেস থেকে সিআই পাইপলাইন রান হিস্ট্রি এবং লগ ফেচ করার সার্ভিস।

import { apiClient } from './apiClient';

export interface CIReport {
  id: number;
  run_id: number;
  run_number: number;
  event_name: string;
  actor: string;
  workflow_name: string;
  status: string;
  runtime_seconds: number;
  commit_sha: string;
  branch: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  jobs_summary: Record<string, any> | null;
  error_logs: string | null;
  created_at: number;
}

export const ciReportService = {
  getCILogs: async (limit: number = 20): Promise<CIReport[]> => {
    // বাংলা মন্তব্য: ব্যাকএন্ডের /admin-api/ci-logs এন্ডপয়েন্ট থেকে সিআই রিপোর্টগুলো পড়া হচ্ছে
    return apiClient.get<CIReport[]>(`/admin-api/ci-logs?limit=${limit}`);
  }
};
