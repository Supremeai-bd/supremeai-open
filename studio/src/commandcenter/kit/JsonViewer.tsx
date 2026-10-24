import { useState } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — JSON Viewer
// বাংলা মন্তব্য: JSON ডেটা ভিউয়ার — collapsible tree
// ═══════════════════════════════════════════════════════════════════════════

interface JsonViewerProps {
  data: unknown;
  level?: number;
  defaultExpanded?: boolean;
}

function JsonNode({ data, level = 0, defaultExpanded = false }: JsonViewerProps) {
  const [expanded, setExpanded] = useState(defaultExpanded || level < 2);

  if (data === null) return <span className="text-[#94a3b8]">null</span>;
  if (typeof data === 'string') return <span className="text-[#10b981]">"{data}"</span>;
  if (typeof data === 'number') return <span className="text-[#00f3ff]">{data}</span>;
  if (typeof data === 'boolean') return <span className="text-[#bc13fe]">{String(data)}</span>;

  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="text-[#94a3b8]">[]</span>;
    return (
      <span>
        <button onClick={() => setExpanded(!expanded)} className="inline-flex items-center text-[var(--sa-text-1)] hover:text-[#00f3ff]">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span className="text-[var(--sa-text-0)]">[{data.length}]</span>
        </button>
        {expanded && (
          <div className="pl-4 border-l border-[var(--sa-line)] ml-1">
            {data.map((item, i) => (
              <div key={i} className="my-0.5">
                <JsonNode data={item} level={level + 1} />
              </div>
            ))}
          </div>
        )}
      </span>
    );
  }

  if (typeof data === 'object') {
    const entries = Object.entries(data as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-[#94a3b8]">{'{}'}</span>;
    return (
      <span>
        <button onClick={() => setExpanded(!expanded)} className="inline-flex items-center text-[var(--sa-text-1)] hover:text-[#00f3ff]">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span className="text-[var(--sa-text-0)]">{'{'}{entries.length}{'}'}</span>
        </button>
        {expanded && (
          <div className="pl-4 border-l border-[var(--sa-line)] ml-1">
            {entries.map(([key, value]) => (
              <div key={key} className="my-0.5">
                <span className="text-[#bc13fe]">{key}</span>
                <span className="text-[var(--sa-text-2)]">: </span>
                <JsonNode data={value} level={level + 1} />
              </div>
            ))}
          </div>
        )}
      </span>
    );
  }

  return <span className="text-[var(--sa-text-0)]">{String(data)}</span>;
}

export function JsonViewer({ data, defaultExpanded }: JsonViewerProps) {
  return (
    <div className="p-3 rounded-xl border border-[var(--sa-line)] bg-[var(--sa-bg-1)] font-mono text-xs overflow-auto max-h-[400px]">
      <JsonNode data={data} defaultExpanded={defaultExpanded} />
    </div>
  );
}
