import type { ReactNode } from 'react';

type MetricCardProps = {
  label: string;
  value: string;
  note: string;
  trend?: string;
  icon: ReactNode;
  tone?: 'cyan' | 'violet' | 'lime' | 'blue';
};

export function MetricCard({ label, value, note, trend, icon, tone = 'cyan' }: MetricCardProps) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <div className="metric-topline">
        <span className="metric-icon">{icon}</span>
        {trend && <span className="metric-trend"><span aria-hidden="true">↗</span> {trend}</span>}
      </div>
      <p className="metric-label">{label}</p>
      <div className="metric-value">{value}</div>
      <p className="metric-note">{note}</p>
    </article>
  );
}
