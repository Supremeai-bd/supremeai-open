import type { CSSProperties } from 'react';

const bars = [34, 45, 38, 62, 50, 57, 46, 71, 55, 66, 48, 76, 61, 70, 54, 83, 68, 88, 64, 79, 58, 74, 68, 92];

export function LiveChart() {
  return (
    <div className="chart-wrap" role="img" aria-label="Illustrative demo activity chart showing a generally rising agent activity trend over the past twelve hours">
      <div className="chart-scale"><span>1.8k</span><span>1.2k</span><span>600</span><span>0</span></div>
      <div className="chart-main">
        <div className="chart-grid"><i /><i /><i /><i /></div>
        <div className="chart-bars">
          {bars.map((height, index) => <span key={index} style={{ '--bar-height': `${height}%`, '--bar-delay': `${index * 35}ms` } as CSSProperties} />)}
        </div>
        <svg className="chart-line" viewBox="0 0 720 150" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="lineGlow" x1="0" y1="0" x2="1" y2="0"><stop stopColor="#00f3ff" stopOpacity=".3" /><stop offset=".52" stopColor="#00f3ff" /><stop offset="1" stopColor="#c9f36b" /></linearGradient>
          </defs>
          <path d="M0 119 C40 117 38 94 80 100 S119 124 153 89 S204 103 234 72 S283 92 316 67 S365 83 396 54 S447 80 475 44 S527 65 558 38 S607 65 641 27 S687 40 720 18" fill="none" stroke="url(#lineGlow)" strokeWidth="2.5" />
          <path d="M0 119 C40 117 38 94 80 100 S119 124 153 89 S204 103 234 72 S283 92 316 67 S365 83 396 54 S447 80 475 44 S527 65 558 38 S607 65 641 27 S687 40 720 18" fill="none" stroke="#00f3ff" strokeOpacity=".28" strokeWidth="8" className="chart-line-blur" />
          <circle cx="641" cy="27" r="5.5" fill="#c9f36b" stroke="#0a0f17" strokeWidth="3" className="chart-end-dot" />
        </svg>
        <div className="chart-x-labels"><span>00:00</span><span>04:00</span><span>08:00</span><span>12:00</span></div>
      </div>
    </div>
  );
}
