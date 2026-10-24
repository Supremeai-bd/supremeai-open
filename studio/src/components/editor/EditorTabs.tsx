import React from 'react';
import { useIdeStore } from '../../store/useIdeStore';
import { X } from 'lucide-react';

export const EditorTabs: React.FC = () => {
  const { files, openFiles, activeFile, setActiveFile, closeFile } = useIdeStore();

  if (openFiles.length === 0) {
    return <div className="flex bg-[#2d2d2d] h-9 border-b border-[#1e1e1e]"></div>;
  }

  return (
    <div className="flex bg-[#2d2d2d] overflow-x-auto no-scrollbar">
      {openFiles.map(path => {
        const file = files[path];
        if (!file) return null;

        const isActive = activeFile === path;

        return (
          <div
            key={path}
            onClick={() => setActiveFile(path)}
            className={`
              flex items-center group cursor-pointer px-3 py-2 min-w-[120px] max-w-[200px] border-r border-[#1e1e1e]
              ${isActive ? 'bg-[#1e1e1e] text-blue-400' : 'bg-[#2d2d2d] text-gray-400 hover:bg-[#252526]'}
            `}
          >
            <span className="truncate flex-1 text-sm">{file.name}</span>
            {file.isModified && <span className="w-2 h-2 rounded-full bg-blue-500 mr-2 ml-1"></span>}

            <button
              onClick={(e) => {
                e.stopPropagation();
                closeFile(path);
              }}
              className={`p-0.5 rounded-md hover:bg-gray-600 ${isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
