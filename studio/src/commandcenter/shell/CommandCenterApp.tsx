import { CommandBar } from './CommandBar';
import { CommandPalette } from './CommandPalette';
import { LeftRail } from './LeftRail';
import { WorkspaceViewport } from './WorkspaceViewport';
import { BottomDeck } from './BottomDeck';
import { useMetrics, useHealthMap } from '../data/hooks';

export function CommandCenterApp() {
  const { data: metrics } = useMetrics(15_000);
  const { data: health } = useHealthMap(45_000);

  return (
    <div className="flex flex-col h-screen bg-[var(--sa-bg-0)] text-[var(--sa-text-0)]">
      <CommandBar
        healthPercent={health?.overall_health_percent ?? null}
      />
      <CommandPalette />
      <div className="flex flex-1 overflow-hidden">
        <LeftRail />
        <WorkspaceViewport />
      </div>
      <BottomDeck metrics={metrics ?? null} />
    </div>
  );
}
