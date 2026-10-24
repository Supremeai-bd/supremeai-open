import { useEffect } from 'react';
import { SkeletonLoader } from '../ui/SkeletonLoader';
import { useCustomerStore } from '../../store/customerStore';

interface Widget {
  id: string;
  title: string;
  content: string;
}

const DEFAULT_WIDGETS: Widget[] = [
  { id: '1', title: 'AI Assistant', content: 'Chat with your AI assistant to get help with coding, debugging, and more.' },
  { id: '2', title: 'Code Snippets', content: 'Save and reuse your favorite code snippets.' },
  { id: '3', title: 'Project Stats', content: 'View statistics about your current project.' },
  { id: '4', title: 'Quick Commands', content: 'Execute common commands with one click.' },
  { id: '5', title: 'Resource Monitor', content: 'Monitor CPU, memory, and network usage.' },
  { id: '6', title: 'Latest News', content: 'Stay updated with the latest AI and tech news.' },
];

export function HomeFeed() {
  const { widgets: storeWidgets, reorderWidgets } = useCustomerStore();
  const isLoading = false; // Data is from store, no loading needed

  // Initialize store with defaults if empty
  useEffect(() => {
    if (!storeWidgets || storeWidgets.length === 0) {
      reorderWidgets(DEFAULT_WIDGETS.map(w => ({
        id: w.id,
        type: 'history' as const,
        title: w.title,
        position: { x: 0, y: 0, w: 1, h: 1 },
        settings: { content: w.content },
      })));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const displayWidgets: Widget[] = (storeWidgets && storeWidgets.length > 0)
    ? storeWidgets.map(w => ({
        id: w.id,
        title: w.title,
        content: (w.settings?.content as string) || '',
      }))
    : DEFAULT_WIDGETS;

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, id: string) => {
    e.dataTransfer.setData('text/plain', id);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, dropId: string) => {
    e.preventDefault();
    const draggedId = e.dataTransfer.getData('text/plain');
    if (draggedId === dropId) return;

    const prev = storeWidgets && storeWidgets.length > 0
      ? storeWidgets
      : DEFAULT_WIDGETS.map(w => ({
          id: w.id,
          type: 'history' as const,
          title: w.title,
          position: { x: 0, y: 0, w: 1, h: 1 },
          settings: { content: w.content },
        }));

    const draggedIndex = prev.findIndex(w => w.id === draggedId);
    const dropIndex = prev.findIndex(w => w.id === dropId);
    if (draggedIndex === -1 || dropIndex === -1) return;

    const newWidgets = [...prev];
    const [draggedWidget] = newWidgets.splice(draggedIndex, 1);
    newWidgets.splice(dropIndex, 0, draggedWidget);
    reorderWidgets(newWidgets);
  };

  return (
    <div className="p-4 bg-[#020205] min-h-[calc(100vh-64px)] overflow-y-auto page-transition-enter-active">
      <h2 className="text-2xl font-bold font-['Space_Grotesk'] tracking-widest mb-6 text-[#f8f9fa]">
        Personalized Home Feed
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-3 p-4 border border-slate-800 rounded-xl bg-slate-900/30">
                <div className="flex gap-2 items-center">
                  <SkeletonLoader type="avatar" className="w-8 h-8" />
                  <SkeletonLoader className="w-32" />
                </div>
                <SkeletonLoader className="w-full mt-2" />
                <SkeletonLoader className="w-3/4" />
              </div>
            ))
          : displayWidgets.map(widget => (
              <div
                key={widget.id}
                draggable
                onDragStart={(e) => handleDragStart(e, widget.id)}
                onDragOver={(e) => handleDragOver(e)}
                onDrop={(e) => handleDrop(e, widget.id)}
                className="glass-card cursor-move p-4 flex flex-col gap-3 glass-hover"
              >
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--neon-blue)]/10 text-[var(--neon-blue)]">
                    <span className="text-[var(--neon-blue)]">🤖</span>
                  </div>
                  <h3 className="font-semibold text-[var(--foreground)]">{widget.title}</h3>
                </div>
                <p className="text-[var(--foreground)]/70 text-sm flex-1">{widget.content}</p>
              </div>
            ))
        }
      </div>
    </div>
  );
}
