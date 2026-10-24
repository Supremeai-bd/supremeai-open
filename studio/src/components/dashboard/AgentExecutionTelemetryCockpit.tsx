import React, { useState, useEffect } from 'react';
import WebSocketManager from '../../services/realtime/WebSocketManager';
import { getWebSocketBaseUrl } from '../../utils/api';
import { getUserToken } from '../../services/tokenStorage';

interface AgentLogEntry {
  timestamp: string;
  level?: string;
  message?: string;
  msg?: string;
}

interface AgentExecutionTelemetryCockpitProps {
  authToken: string;
}

const AgentExecutionTelemetryCockpit: React.FC<AgentExecutionTelemetryCockpitProps> = ({ authToken }) => {
  const [activeTab, setActiveTab] = useState<'fileTree' | 'executionShell' | 'agentLog'>('fileTree');
  // Audit F-01 fix: file index stays empty until the file-index API is wired.
  const [files] = useState<string[]>([]);
  const [shellHistory, setShellHistory] = useState<string[]>([]);
  const [agentLogs, setAgentLogs] = useState<AgentLogEntry[]>([]);
  const [currentCommand, setCurrentCommand] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [executionState, setExecutionState] = useState<'idle' | 'running' | 'paused' | 'error' | 'completed'>('idle');
  const [timelinePosition, setTimelinePosition] = useState(0);
  const [agentState, setAgentState] = useState<'thinking' | 'planning' | 'executing' | 'reviewing' | 'communicating' | 'waiting' | 'analyzing' | 'learning'>('thinking');

  // Initialize the agent telemetry stream for real-time log updates
  useEffect(() => {
    // SECURITY FIX (audit S-2): token removed from URL; sent as first-message auth frame.
    const baseUrl = getWebSocketBaseUrl();
    // FIX (API-contract audit): realtime_dashboard.py serves /ws/dashboard
    // (prefix /ws). The old /api/ws/dashboard path matched no backend route.
    const wsUrl = `${baseUrl}/ws/dashboard`;
    const wsManager = new WebSocketManager(wsUrl, {
      onOpen: () => {
        // Send auth frame immediately on connect — never in the URL.
        // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
        const token = authToken || getUserToken();
        if (token) {
          // WebSocketManager.send is called via its internal ws; use onOpen callback
          // to trigger the first-message auth right after the socket opens.
          // We rely on the wsManager's own ws reference through the callback.
          wsManager.send(JSON.stringify({ type: 'auth', payload: { token } }));
        }
        console.warn('Connected to agent telemetry WebSocket');
        setIsConnected(true);
      },
      onClose: () => {
        console.warn('Disconnected from agent telemetry WebSocket');
        setIsConnected(false);
      },
      onMessage: (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'log_entry') {
            setAgentLogs(prev => [...prev.slice(-49), { ...data.payload, timestamp: new Date().toISOString() }]);
          } else if (data.type === 'execution_state') {
            setExecutionState(data.payload.state);
          } else if (data.type === 'agent_state') {
            setAgentState(data.payload.state);
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      }
    });

    wsManager.connect();

    // Cleanup on unmount
    return () => {
      wsManager.disconnect();
    };
  }, [authToken]);

  // Audit F-01 fix (2026-09-17): the hardcoded mock file tree was removed —
  // the workspace file-index API is not wired yet, so the File Explorer shows
  // an honest empty state instead of a fabricated repository tree.
  const handleExecuteCommand = () => {
    if (!currentCommand.trim()) return;

    // Audit F-01 fix: the shell previously SIMULATED execution with a
    // setTimeout that always printed "Operation completed successfully." —
    // a fake terminal on a live route. No backend command-execution channel
    // is wired, so the honest response is an explicit unavailability notice;
    // execution state stays untouched (never fake 'running'/'completed').
    setShellHistory(prev => [...prev, `$ ${currentCommand}`]);
    setShellHistory(prev => [
      ...prev,
      '[unavailable] Command execution is not wired to the backend yet. This cockpit '
        + 'displays live telemetry only (Agent Log, execution state, agent state).',
    ]);
    setCurrentCommand('');
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleExecuteCommand();
    }
  };

  const agentStates = [
    { name: 'thinking', label: 'Thinking', color: 'bg-blue-500' },
    { name: 'planning', label: 'Planning', color: 'bg-purple-500' },
    { name: 'executing', label: 'Executing', color: 'bg-green-500' },
    { name: 'reviewing', label: 'Reviewing', color: 'bg-yellow-500' },
    { name: 'communicating', label: 'Communicating', color: 'bg-indigo-500' },
    { name: 'waiting', label: 'Waiting', color: 'bg-gray-500' },
    { name: 'analyzing', label: 'Analyzing', color: 'bg-orange-500' },
    { name: 'learning', label: 'Learning', color: 'bg-pink-500' }
  ];

  return (
    <div className="flex flex-col h-full bg-gray-900 text-white">
      {/* Header */}
      <div className="flex items-center justify-between p-4 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center space-x-4">
          <h1 className="text-xl font-bold text-cyan-400">Agent Execution Telemetry</h1>
          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
          <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-sm">
            Execution: <span className={`font-mono ${executionState === 'running' ? 'text-green-400' : executionState === 'error' ? 'text-red-400' : 'text-gray-400'}`}>
              {executionState.toUpperCase()}
            </span>
          </div>
          <div className="text-sm">
            Agent: <span className="font-mono text-purple-400">{agentState}</span>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Panel - File Tree */}
        <div className={`w-1/3 border-r border-gray-700 flex flex-col ${activeTab === 'fileTree' ? 'block' : 'hidden md:block'}`}>
          <div className="p-2 bg-gray-800 border-b border-gray-700">
            <h2 className="font-semibold text-cyan-300">File Explorer</h2>
          </div>
          <div className="flex-1 overflow-y-auto p-2 bg-gray-850">
            {files.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-4">
                <p className="text-sm text-gray-400 font-medium">File index unavailable</p>
                <p className="text-xs text-gray-500 mt-2 max-w-[220px]">
                  The workspace file-index API is not wired to this cockpit yet, so no
                  repository tree is shown (no mock data).
                </p>
              </div>
            ) : (
              <ul className="text-sm">
                {files.map((file, index) => (
                  <li
                    key={index}
                    className={`py-1 px-2 hover:bg-gray-750 rounded cursor-pointer ${
                      file.trim().endsWith('.tsx') || file.trim().endsWith('.py') ? 'text-green-400' :
                      file.trim().endsWith('/') ? 'text-blue-400 font-medium' : 'text-gray-300'
                    }`}
                  >
                    {file}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Center Panel - Execution Shell */}
        <div className={`w-1/3 border-r border-gray-700 flex flex-col ${activeTab === 'executionShell' ? 'block' : 'hidden md:block'}`}>
          <div className="p-2 bg-gray-800 border-b border-gray-700">
            <h2 className="font-semibold text-cyan-300">Execution Shell</h2>
          </div>
          <div className="flex-1 overflow-y-auto p-2 font-mono text-sm bg-black bg-opacity-30">
            <div className="h-full flex flex-col">
              <div className="flex-1 overflow-y-auto mb-2">
                {shellHistory.map((entry, index) => (
                  <div
                    key={index}
                    className={`py-1 ${entry.startsWith('$') ? 'text-green-400' : 'text-gray-300'}`}
                  >
                    {entry}
                  </div>
                ))}
              </div>
              <div className="flex items-center mt-auto">
                <span className="text-green-400 mr-2">$</span>
                <input
                  type="text"
                  value={currentCommand}
                  onChange={(e) => setCurrentCommand(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Command execution not wired yet..."
                  className="flex-1 bg-gray-800 text-white px-2 py-1 rounded border border-gray-600 focus:outline-none focus:border-cyan-500"
                />
                <button
                  onClick={handleExecuteCommand}
                  className="ml-2 px-3 py-1 bg-cyan-600 hover:bg-cyan-700 rounded text-sm"
                >
                  Run
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Right Panel - Agent Log */}
        <div className={`w-1/3 flex flex-col ${activeTab === 'agentLog' ? 'block' : 'hidden md:block'}`}>
          <div className="p-2 bg-gray-800 border-b border-gray-700 flex justify-between items-center">
            <h2 className="font-semibold text-cyan-300">Agent Log</h2>
            <button
              onClick={() => setAgentLogs([])}
              className="text-xs bg-red-600 hover:bg-red-700 px-2 py-1 rounded"
            >
              Clear
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 font-mono text-xs bg-black bg-opacity-30">
            {agentLogs.map((log, index) => (
              <div key={index} className={`py-1 border-b border-gray-800 ${log.level === 'ERROR' ? 'text-red-400' : log.level === 'WARN' ? 'text-yellow-400' : 'text-gray-300'}`}>
                <span className="text-gray-500 mr-2">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                <span>[{log.level || 'INFO'}]</span> {log.message || log.msg}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Timeline Scrubber */}
      <div className="p-2 bg-gray-800 border-t border-gray-700">
        <div className="flex items-center">
          <span className="text-sm mr-2">Timeline:</span>
          <input
            type="range"
            min="0"
            max="100"
            value={timelinePosition}
            onChange={(e) => setTimelinePosition(parseInt(e.target.value))}
            className="flex-1"
          />
          <span className="text-sm ml-2 w-12">{timelinePosition}%</span>
        </div>
      </div>

      {/* Agent State Display */}
      <div className="p-2 bg-gray-800 border-t border-gray-700">
        <div className="flex flex-wrap gap-2">
          {agentStates.map((state) => (
            <div
              key={state.name}
              className={`px-3 py-1 rounded-full text-xs font-medium flex items-center ${
                agentState === state.name
                  ? `${state.color} text-white ring-2 ring-offset-2 ring-offset-gray-800 ring-white`
                  : 'bg-gray-700 text-gray-300'
              }`}
            >
              <span className={`w-2 h-2 rounded-full mr-2 ${agentState === state.name ? 'bg-white' : state.color}`}></span>
              {state.label}
            </div>
          ))}
        </div>
      </div>

      {/* Bottom Tab Navigation */}
      <div className="flex border-t border-gray-700 bg-gray-800">
        <button
          className={`flex-1 py-2 text-center ${activeTab === 'fileTree' ? 'bg-cyan-900 text-cyan-300' : 'hover:bg-gray-700'}`}
          onClick={() => setActiveTab('fileTree')}
        >
          File Tree
        </button>
        <button
          className={`flex-1 py-2 text-center ${activeTab === 'executionShell' ? 'bg-cyan-900 text-cyan-300' : 'hover:bg-gray-700'}`}
          onClick={() => setActiveTab('executionShell')}
        >
          Execution Shell
        </button>
        <button
          className={`flex-1 py-2 text-center ${activeTab === 'agentLog' ? 'bg-cyan-900 text-cyan-300' : 'hover:bg-gray-700'}`}
          onClick={() => setActiveTab('agentLog')}
        >
          Agent Log
        </button>
      </div>
    </div>
  );
};

export default AgentExecutionTelemetryCockpit;
