import React, { useEffect, useState } from 'react';
import { useIdeStore } from '../../store/useIdeStore';
import { FileCode, Folder, FolderOpen, ChevronRight, ChevronDown } from 'lucide-react';

interface FileNode {
  name: string;
  isDirectory: boolean;
  path: string;
  children?: FileNode[];
}

export const FileExplorer: React.FC = () => {
  const { webContainer, openFile } = useIdeStore();
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['/']));

  useEffect(() => {
    if (!webContainer) return;

    const loadFiles = async () => {
      try {
        const rootEntries = await webContainer.fs.readdir('/', { withFileTypes: true });

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const buildTree = async (entries: any[], currentPath: string): Promise<FileNode[]> => {
          const nodes: FileNode[] = [];
          for (const entry of entries) {
            const path = `${currentPath === '/' ? '' : currentPath}/${entry.name}`;
            const isDir = entry.isDirectory();

            nodes.push({
              name: entry.name,
              isDirectory: isDir,
              path: path,
              children: isDir ? [] : undefined // We can lazy load or deep load. Deep load for simplicity now.
            });
          }
          return nodes.sort((a, b) => {
            if (a.isDirectory === b.isDirectory) return a.name.localeCompare(b.name);
            return a.isDirectory ? -1 : 1;
          });
        };

        const tree = await buildTree(rootEntries, '/');
        setFileTree(tree);
      } catch (err) {
        console.error("Failed to load file tree", err);
      }
    };

    loadFiles();
  }, [webContainer]);

  const toggleFolder = (path: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
      // If we were lazy loading, we'd fetch contents here
    }
    setExpandedFolders(newExpanded);
  };

  const handleFileClick = async (node: FileNode) => {
    if (node.isDirectory) {
      toggleFolder(node.path);
    } else {
      if (webContainer) {
        try {
          const content = await webContainer.fs.readFile(node.path, 'utf-8');
          const ext = node.name.split('.').pop() || '';
          const langMap: Record<string, string> = {
            'js': 'javascript', 'ts': 'typescript', 'json': 'json', 'html': 'html', 'css': 'css', 'md': 'markdown'
          };

          openFile({
            path: node.path,
            name: node.name,
            content: content,
            language: langMap[ext] || 'plaintext',
            isModified: false
          });
        } catch (err) {
          console.error("Error reading file", err);
        }
      }
    }
  };

  const renderTree = (nodes: FileNode[], depth = 0) => {
    return nodes.map(node => {
      const isExpanded = expandedFolders.has(node.path);
      return (
        <div key={node.path} className="select-none">
          <div
            className={`flex items-center px-2 py-1 cursor-pointer hover:bg-gray-700 text-sm text-gray-300 ${depth > 0 ? 'ml-4' : ''}`}
            onClick={() => handleFileClick(node)}
          >
            {node.isDirectory ? (
              <>
                {isExpanded ? <ChevronDown size={14} className="mr-1" /> : <ChevronRight size={14} className="mr-1" />}
                {isExpanded ? <FolderOpen size={16} className="text-blue-400 mr-2" /> : <Folder size={16} className="text-blue-400 mr-2" />}
              </>
            ) : (
              <>
                <FileCode size={16} className="text-gray-400 mr-2 ml-4" />
              </>
            )}
            <span className="truncate">{node.name}</span>
          </div>
          {node.isDirectory && isExpanded && node.children && (
            <div>{renderTree(node.children, depth + 1)}</div>
          )}
        </div>
      );
    });
  };

  return (
    <div className="flex flex-col h-full bg-[#252526] text-gray-300 border-r border-gray-700">
      <div className="p-2 text-xs font-semibold tracking-wider text-gray-400 uppercase border-b border-gray-700">
        Explorer
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {fileTree.length === 0 ? (
          <div className="text-center text-xs text-gray-500 mt-10">No files in WebContainer</div>
        ) : (
          renderTree(fileTree)
        )}
      </div>
    </div>
  );
};
