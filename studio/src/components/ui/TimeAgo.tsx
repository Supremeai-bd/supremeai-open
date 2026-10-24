/**
 * TimeAgo — #2736: self-ticking leaf "relative time" renderer.
 *
 * বাংলা মন্তব্য: আগে প্যানেল-লেভেল `setInterval(setNowEpoch, 1_000)` পুরো
 * node-list প্রতি সেকেন্ডে re-render করত (select/state সহ)। এখন tick-এর
 * মালিকানা এই leaf-এই — parent re-render হয় না, শুধু এই span বদলায়।
 * 30s tick: উপস্থিতি-টেক্সটের জন্য যথেষ্ট রেজোলিউশন (MeshAgentsPanel-এর
 * presence TTL 10 মিনিট — 1s নির্ভুলতা প্রয়োজন ছিল না)।
 */
import { useEffect, useState, type ReactNode } from 'react';

const DEFAULT_TICK_MS = 30_000;

/** Leaf-owned clock — 30s পরপর শুধু নিজেই re-render। */
export function useNowEpoch(tickMs: number = DEFAULT_TICK_MS): number {
  const [nowEpoch, setNowEpoch] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const t = setInterval(() => setNowEpoch(Date.now() / 1000), tickMs);
    return () => clearInterval(t);
  }, [tickMs]);
  return nowEpoch;
}

export interface TimeAgoProps {
  /** Event time in epoch-seconds. */
  epoch: number;
  /**
   * Injectable "now" (epoch-seconds) — টেস্টে deterministic age দেওয়ার জন্য;
   * বাদ দিলে leaf-এর নিজস্ব 30s clock ব্যবহার হয়।
   */
  nowEpoch?: number;
  /** Render-prop: age-নির্ভর UI (badge + টেক্সট) leaf-এর ভেতরেই বাঁধা থাকে। */
  children: (ageSec: number) => ReactNode;
  className?: string;
}

export function TimeAgo({ epoch, nowEpoch, children, className }: TimeAgoProps) {
  const internalNow = useNowEpoch();
  const now = nowEpoch ?? internalNow;
  const ageSec = Math.max(0, Math.round(now - epoch));
  return <span className={className}>{children(ageSec)}</span>;
}

export default TimeAgo;
