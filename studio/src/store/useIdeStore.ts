import { create } from 'zustand';
import type { WebContainer } from '@webcontainer/api';

export interface IdeFile {
  path: string;
  name: string;
  content: string;
  language: string;
  isModified: boolean;
}

interface IdeState {
  webContainer: WebContainer | null;
  setWebContainer: (instance: WebContainer) => void;

  files: Record<string, IdeFile>;
  openFiles: string[];
  activeFile: string | null;

  setActiveFile: (path: string) => void;
  openFile: (file: IdeFile) => void;
  closeFile: (path: string) => void;
  updateFileContent: (path: string, content: string) => void;
  markFileSaved: (path: string) => void;
}

export const useIdeStore = create<IdeState>((set) => ({
  webContainer: null,
  setWebContainer: (instance) => set({ webContainer: instance }),

  files: {},
  openFiles: [],
  activeFile: null,

  setActiveFile: (path) => set({ activeFile: path }),

  openFile: (file) => set((state) => {
    const updatedFiles = { ...state.files, [file.path]: file };
    const updatedOpenFiles = state.openFiles.includes(file.path)
      ? state.openFiles
      : [...state.openFiles, file.path];

    return {
      files: updatedFiles,
      openFiles: updatedOpenFiles,
      activeFile: file.path
    };
  }),

  closeFile: (path) => set((state) => {
    const newOpenFiles = state.openFiles.filter(p => p !== path);
    return {
      openFiles: newOpenFiles,
      activeFile: state.activeFile === path
        ? (newOpenFiles.length > 0 ? newOpenFiles[newOpenFiles.length - 1] : null)
        : state.activeFile
    };
  }),

  updateFileContent: (path, content) => set((state) => {
    const file = state.files[path];
    if (!file) return state;
    return {
      files: {
        ...state.files,
        [path]: { ...file, content, isModified: true }
      }
    };
  }),

  markFileSaved: (path) => set((state) => {
    const file = state.files[path];
    if (!file) return state;
    return {
      files: {
        ...state.files,
        [path]: { ...file, isModified: false }
      }
    };
  })
}));
