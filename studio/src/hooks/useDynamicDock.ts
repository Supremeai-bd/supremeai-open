export function useDynamicDock() {
  return {
    dockItems: [] as any[],
    activeItem: null as any,
    setActiveItem: (item: any) => {},
    isOpen: true,
  };
}
export default useDynamicDock;
