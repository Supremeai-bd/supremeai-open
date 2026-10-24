import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { motion, AnimatePresence } from 'framer-motion';
import './admin-hud.css';

interface AethelNodeProps {
  data: {
    label: string | React.ReactNode;
    status?: 'Nominal' | 'Warning' | 'Critical';
    type?: 'orb' | 'swarm' | 'mesh' | 'firewall' | 'evolution' | 'gateway' | 'memory' | 'cicd' | 'deploy' | 'analytics' | 'network' | 'kubernetes' | 'security' | 'instances' | 'storage' | 'aplgw' | 'aplsw';
  };
  isConnectable: boolean;
}

// বাংলা মন্তব্য: কাস্টম এথেল নোড কম্পোনেন্ট — সব থিমের সাথে সামঞ্জস্যপূর্ণ CSS ভ্যারিয়েবল ব্যবহার করা হচ্ছে
const AethelNode = ({ data, isConnectable }: AethelNodeProps) => {
  const [isHovered, setIsHovered] = React.useState(false);

  const getGlowClass = (type?: string) => {
    switch (type) {
      case 'swarm':
      case 'analytics':
      case 'aplgw':
      case 'deploy':
        return 'glow-cyan';
      case 'mesh':
      case 'cicd':
      case 'kubernetes':
      case 'instances':
        return 'glow-green';
      case 'firewall':
      case 'security':
      case 'memory':
      case 'storage':
      case 'aplsw':
        return 'glow-gold';
      default:
        return 'glow-cyan';
    }
  };

  const getStatusColor = (status?: string) => {
    if (status === 'Critical') return 'bg-rose-500 shadow-[0_0_8px_#f43f5e]';
    if (status === 'Warning') return 'bg-amber-500 shadow-[0_0_8px_#f59e0b]';
    return 'bg-emerald-500 shadow-[0_0_8px_#10b981]';
  };

  return (
    <motion.div
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      whileHover={{ scale: 1.05 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={`aethel-node ${getGlowClass(data.type)} group relative min-w-[130px]`}
    >
      <Handle type="target" position={Position.Left} isConnectable={isConnectable} className="!bg-[var(--accent-primary)] !w-2 !h-2 !border-none" />

      {/* Holographic Tooltip */}
      <AnimatePresence>
        {isHovered && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.9 }}
            transition={{ duration: 0.2 }}
            className="absolute -top-10 left-1/2 -translate-x-1/2 z-50 pointer-events-none"
          >
            <div className="bg-[var(--bg-main)] border border-[var(--border-accent)] text-[var(--accent-primary)] text-[8px] px-2 py-1 rounded backdrop-blur-md whitespace-nowrap shadow-lg font-mono transition-colors duration-500">
               SYS TELEMETRY: {data.status || 'Nominal'}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex flex-col gap-1 w-full">
        {/* Node Category & Status Light */}
        <div className="flex justify-between items-center w-full pb-1 border-b border-[var(--border-accent)] mb-1 transition-colors duration-500">
          <span className="text-[8px] font-bold text-[var(--text-secondary)] font-mono tracking-wider uppercase">
            {data.type || 'SYSTEM'}
          </span>
          <span className={`w-1.5 h-1.5 rounded-full ${getStatusColor(data.status)}`} />
        </div>

        {/* Main Content */}
        <div className="text-[10px] font-bold text-[var(--node-text)] w-full truncate">
          {data.label}
        </div>
      </div>

      <Handle type="source" position={Position.Right} isConnectable={isConnectable} className="!bg-[var(--accent-primary)] !w-2 !h-2 !border-none" />
    </motion.div>
  );
};

export const SciFiFlowNode = memo(AethelNode);
export { SciFiFlowNode as AethelNode };
export default SciFiFlowNode;
