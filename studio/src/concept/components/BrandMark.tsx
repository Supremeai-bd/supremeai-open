export function BrandMark() {
  return (
    <div className="brand-mark" aria-label="SupremeAI">
      <span className="brand-glyph" aria-hidden="true">
        <svg viewBox="0 0 40 40" fill="none">
          <circle cx="20" cy="20" r="15" stroke="currentColor" strokeWidth="1.25" />
          <ellipse cx="20" cy="20" rx="7" ry="15" stroke="currentColor" strokeWidth="1.05" opacity=".7" />
          <path d="M5 20h30M8.7 11.6h22.6M8.7 28.4h22.6" stroke="currentColor" strokeWidth=".9" opacity=".55" />
          <circle cx="30.7" cy="11.4" r="2.2" fill="#c9f36b" className="brand-orbit-dot" />
        </svg>
      </span>
      <span className="brand-word">SUPREME<span>AI</span></span>
    </div>
  );
}
