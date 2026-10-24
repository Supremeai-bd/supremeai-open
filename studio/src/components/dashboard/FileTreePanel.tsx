import React, { useEffect, useRef, useState } from 'react';
import { ChevronRight, ChevronDown, FileText, Folder, FileJson, FileCode, Trash2, Plus } from 'lucide-react';
import { useSessionCockpitStore, type FileNode } from '../../store/sessionCockpitStore';

export const FileTreePanel: React.FC = () => {
  const { fileTreeData } = useSessionCockpitStore();

  // By using useRef<Map>, we avoid triggering React renders for every single patch.
  // We only force a re-render when we specifically want to update the tree view (e.g. via a throttled update).
  const treeRef = useRef<Map<string, FileNode>>(new Map());
  const [treeMap, setTreeMap] = useState<Map<string, FileNode>>(new Map());
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(['/']));

  useEffect(() => {
    // In a real implementation, fileTreeData updates from SSE would populate treeRef.
    // Here we simulate an initial root.
    if (!treeRef.current.has('/')) {
      treeRef.current.set('/', { name: 'workspace', path: '/', type: 'directory', status: 'unchanged' });
      setTreeMap(new Map(treeRef.current));
    }

  }, [fileTreeData]);

  // Clean up on unmount or session reset is handled by the store, but we also clear the ref here.
  useEffect(() => {
    const currentTreeRef = treeRef.current;
    return () => {
      currentTreeRef.clear();
    };

  }, []);

  const toggleFolder = (path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const getIcon = (node: FileNode) => {
    if (node.type === 'directory') return <Folder className="w-4 h-4 text-blue-400" />;
    if (node.name.endsWith('.json')) return <FileJson className="w-4 h-4 text-yellow-400" />;
    if (node.name.endsWith('.ts') || node.name.endsWith('.js')) return <FileCode className="w-4 h-4 text-emerald-400" />;
    return <FileText className="w-4 h-4 text-gray-400" />;
  };

  const getStatusColor = (status: FileNode['status']) => {
    switch (status) {
      case 'new': return 'text-emerald-400 bg-emerald-400/10';
      case 'modified': return 'text-yellow-400 bg-yellow-400/10';
      case 'deleted': return 'text-red-400 line-through opacity-50';
      default: return 'text-gray-300 hover:bg-gray-800';
    }
  };

  const renderNode = (path: string, depth: number = 0) => {
    const node = treeMap.get(path);
    if (!node) return null;

    const isExpanded = expandedFolders.has(path);
    const children = Array.from(treeMap.values()).filter(n => {
      if (n.path === path) return false;
      const parentPath = n.path.substring(0, n.path.lastIndexOf('/')) || '/';
      return parentPath === path;
    });

    return (
      <div key={path}>
        <div
          className={`flex items-center py-1 px-2 cursor-pointer select-none text-sm ${getStatusColor(node.status)}`}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          onClick={() => node.type === 'directory' && toggleFolder(path)}
        >
          <span className="w-4 h-4 mr-1 flex items-center justify-center">
            {node.type === 'directory' && (
              isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />
            )}
          </span>
          {getIcon(node)}
          <span className="ml-2 font-mono truncate">{node.name}</span>
          {node.status === 'new' && <Plus className="w-3 h-3 ml-auto text-emerald-500" />}
          {node.status === 'deleted' && <Trash2 className="w-3 h-3 ml-auto text-red-500" />}
        </div>

        {isExpanded && node.type === 'directory' && (
          <div>
            {children.map(child => renderNode(child.path, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-[#1e1e1e] border-r border-gray-800 overflow-hidden">
      <div className="flex items-center px-4 py-2 bg-[#252526] border-b border-gray-800">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Workspace</h3>
      </div>
      <div className="flex-1 overflow-y-auto overflow-x-hidden py-2 custom-scrollbar">
        {renderNode('/')}
      </div>
    </div>
  );
};
