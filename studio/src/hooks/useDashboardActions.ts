export function useDashboardActions() {
  return {
    dispatchAction: (action: string, payload?: any) => {},
    actions: [] as string[],
    loading: false,
  };
}
export default useDashboardActions;
