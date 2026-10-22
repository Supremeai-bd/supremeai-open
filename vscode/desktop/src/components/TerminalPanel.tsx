import React, { useEffect, useRef } from "react";

export interface TerminalPanelProps {
  lines?: string[];
}

export function TerminalPanel({ lines = [] }: TerminalPanelProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let term: any;
    let fit: any;
    (async () => {
      const { Terminal } = await import("xterm");
      const { FitAddon } = await import("xterm-addon-fit");
      term = new Terminal({ theme: { background: "#0d0f12" } });
      fit = new FitAddon();
      term.loadAddon(fit);
      if (ref.current) {
        term.open(ref.current);
        fit.fit();
      }
      lines.forEach((l) => term.writeln(l));
    })();
    return () => {
      term?.dispose();
    };
  }, [lines]);

  return <div ref={ref} className="h-full w-full" />;
}
