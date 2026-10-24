import type { CISummaryData } from './CIDashboard';

export function convertToCSV(data: CISummaryData): string {
  const headers = ['Job Name', 'Status', 'Duration (s)', 'Errors', 'Warnings'];
  const rows = data.jobs.map(job => [
    job.name,
    job.status,
    job.duration.toString(),
    job.error_count.toString(),
    job.warning_count.toString(),
  ]);
  
  return [headers, ...rows].map(row => row.join(',')).join('\n');
}
