import { describe, it, expect, beforeEach } from 'vitest';

const { useIdeStore } = await import('./useIdeStore');

const reset = () =>
  useIdeStore.setState({
    webContainer: null,
    files: {},
    openFiles: [],
    activeFile: null,
  });

describe('useIdeStore', () => {
  beforeEach(reset);

  it('sets the web container instance', () => {
    const container = { id: 'container' } as never;
    useIdeStore.getState().setWebContainer(container);
    expect(useIdeStore.getState().webContainer).toBe(container);
  });

  it('opens a file and tracks it as active', () => {
    const file = { path: '/a.ts', name: 'a.ts', content: 'x', language: 'ts', isModified: false };
    useIdeStore.getState().openFile(file);
    const state = useIdeStore.getState();
    expect(state.files['/a.ts']).toEqual(file);
    expect(state.openFiles).toEqual(['/a.ts']);
    expect(state.activeFile).toBe('/a.ts');
  });

  it('does not duplicate open files when reopening', () => {
    const file = { path: '/a.ts', name: 'a.ts', content: 'x', language: 'ts', isModified: false };
    useIdeStore.getState().openFile(file);
    useIdeStore.getState().openFile(file);
    expect(useIdeStore.getState().openFiles).toEqual(['/a.ts']);
  });

  it('closes a file and clears active when it was active', () => {
    const a = { path: '/a.ts', name: 'a.ts', content: 'x', language: 'ts', isModified: false };
    const b = { path: '/b.ts', name: 'b.ts', content: 'y', language: 'ts', isModified: false };
    useIdeStore.getState().openFile(a);
    useIdeStore.getState().openFile(b);
    useIdeStore.getState().closeFile('/b.ts');
    const state = useIdeStore.getState();
    expect(state.openFiles).toEqual(['/a.ts']);
    expect(state.activeFile).toBe('/a.ts');
  });

  it('updates file content and marks it modified', () => {
    const file = { path: '/a.ts', name: 'a.ts', content: 'x', language: 'ts', isModified: false };
    useIdeStore.getState().openFile(file);
    useIdeStore.getState().updateFileContent('/a.ts', 'changed');
    expect(useIdeStore.getState().files['/a.ts'].content).toBe('changed');
    expect(useIdeStore.getState().files['/a.ts'].isModified).toBe(true);
  });

  it('ignores content updates for unknown files', () => {
    useIdeStore.getState().updateFileContent('/missing.ts', 'z');
    expect(useIdeStore.getState().files['/missing.ts']).toBeUndefined();
  });

  it('marks a file as saved', () => {
    const file = { path: '/a.ts', name: 'a.ts', content: 'x', language: 'ts', isModified: true };
    useIdeStore.getState().openFile(file);
    useIdeStore.getState().markFileSaved('/a.ts');
    expect(useIdeStore.getState().files['/a.ts'].isModified).toBe(false);
  });
});
