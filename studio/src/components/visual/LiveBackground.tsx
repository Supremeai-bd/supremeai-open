// (#4138 Phase 1) LiveBackground — থিম-সচেতন জীবন্ত ব্যাকগ্রাউন্ড স্তর।
// বাংলা মন্তব্য: Constitution Rule #1 (Existing Capability Before New Code) —
// নতুন particle-লাইব্রেরি নয়; framer-motion (ইতিমধ্যে dep) + CSS vars দিয়ে তৈরি।
// নকশা-নীতি:
//   1. রঙ সব থিম-CSS-vars (var(--neon-blue)/var(--neon-purple)) থেকে — ৮ থিমে
//      স্বয়ংক্রিয় অনুসরণ করে, কম্পোনেন্টে একটি রঙও হার্ডকোড নেই।
//   2. কণার অবস্থান deterministic (fixed টেবিল) — Math.random নয়, তাই
//      re-render/hydration-এ স্থিতিশীল এবং টেস্ট-সম্ভাব্য।
//   3. অ্যানিমেশন শুধু transform/opacity — GPU-friendly, layout-thrash নেই।
//   4. prefers-reduced-motion হলে স্তর রেন্ডার হবে স্থির অবস্থায় (WCAG)।
//   5. pointer-events: none — কনটেন্টের ক্লিক/টাইপে কখনোই বাধা দেয় না।

import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';

export type LiveBackgroundVariant = 'public' | 'workspace';

interface OrbSpec {
  className: string;
  size: number; // rem
  left: string;
  top: string;
  drift: { x: number; y: number }; // px — লুপের দূরত্ব
  duration: number; // সেকেন্ড — ধীর = শান্ত
  delay: number;
}

interface MoteSpec {
  size: number; // px
  left: string;
  top: string;
  duration: number;
  delay: number;
}

// বাংলা মন্তব্য: public-ভ্যারিয়েন্ট = অতিথি-পৃষ্ঠার জন্য দৃশ্যমান নিয়ন-আভা +
// বিরল ভাসমান কণা; workspace-ভ্যারিয়েন্ট = ঘন ড্যাশবোর্ডের পেছনে ফিকে শুধু-অরব।
// উভয়ই fixed-টেবিল — deterministic, টেস্ট-চুক্তি LiveBackground.test.tsx।
const ORBS: Record<LiveBackgroundVariant, OrbSpec[]> = {
  public: [
    { className: 'live-bg-orb-primary', size: 34, left: '12%', top: '18%', drift: { x: 46, y: 30 }, duration: 26, delay: 0 },
    { className: 'live-bg-orb-secondary', size: 28, left: '68%', top: '58%', drift: { x: -38, y: -26 }, duration: 32, delay: 2 },
  ],
  workspace: [
    { className: 'live-bg-orb-primary', size: 26, left: '18%', top: '22%', drift: { x: 26, y: 18 }, duration: 38, delay: 0 },
    { className: 'live-bg-orb-secondary', size: 20, left: '70%', top: '62%', drift: { x: -20, y: -14 }, duration: 44, delay: 3 },
  ],
};

const PUBLIC_MOTES: MoteSpec[] = [
  { size: 3, left: '8%', top: '12%', duration: 18, delay: 0 },
  { size: 2, left: '22%', top: '70%', duration: 22, delay: 1.5 },
  { size: 3, left: '35%', top: '30%', duration: 20, delay: 0.8 },
  { size: 2, left: '48%', top: '82%', duration: 26, delay: 2.2 },
  { size: 3, left: '58%', top: '15%', duration: 19, delay: 1.1 },
  { size: 2, left: '72%', top: '45%', duration: 24, delay: 3 },
  { size: 3, left: '85%', top: '25%', duration: 21, delay: 0.4 },
  { size: 2, left: '93%', top: '65%', duration: 28, delay: 2.6 },
  { size: 2, left: '15%', top: '45%', duration: 23, delay: 1.8 },
  { size: 3, left: '65%', top: '8%', duration: 25, delay: 0.6 },
  { size: 2, left: '40%', top: '55%', duration: 27, delay: 3.4 },
  { size: 2, left: '78%', top: '88%', duration: 30, delay: 1.2 },
];

export interface LiveBackgroundProps {
  variant?: LiveBackgroundVariant;
}

export function LiveBackground({ variant = 'public' }: LiveBackgroundProps) {
  // বাংলা মন্তব্য: useReducedMotion — framer-motion-এর built-in media-query hook।
  // reduced-motion চাইলে অ্যানিমেশন-লুপ একেবারে বন্ধ; স্তরটি স্থির থাকে
  // (CSS @media backstop-ও আছে index.css-এ)।
  const prefersReducedMotion = useReducedMotion();
  const orbs = ORBS[variant];
  const motes = variant === 'public' ? PUBLIC_MOTES : [];

  return (
    <div className="live-bg" data-testid={`live-bg-${variant}`} aria-hidden="true">
      {orbs.map((orb) => (
        <motion.div
          key={orb.className}
          className={`live-bg-orb ${orb.className}`}
          style={{ width: `${orb.size}rem`, height: `${orb.size}rem`, left: orb.left, top: orb.top }}
          animate={
            prefersReducedMotion
              ? undefined
              : { x: [0, orb.drift.x, 0], y: [0, orb.drift.y, 0] }
          }
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: orb.duration, delay: orb.delay, repeat: Infinity, ease: 'easeInOut' }
          }
        />
      ))}
      {motes.map((mote, index) => (
        <motion.div
          key={`live-bg-mote-${index}`}
          className="live-bg-mote"
          style={{ width: mote.size, height: mote.size, left: mote.left, top: mote.top }}
          animate={
            prefersReducedMotion
              ? undefined
              : { y: [0, -14, 0], opacity: [0.2, 0.45, 0.2] }
          }
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: mote.duration, delay: mote.delay, repeat: Infinity, ease: 'easeInOut' }
          }
        />
      ))}
    </div>
  );
}
