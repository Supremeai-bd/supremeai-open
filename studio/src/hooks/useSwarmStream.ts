import { useContext } from 'react';
// বাংলা মন্তব্য: SwarmHealthContext একে অপর ফাইল থেকে ইম্পোর্ট করা হয়েছে, যাতে react-refresh সতর্কতা দূর হয়
import { SwarmHealthContext } from '../providers/SwarmHealthContext';
import type { SwarmContextState } from '../types/swarm';

export const useSwarmStream = (): SwarmContextState => {
  const context = useContext(SwarmHealthContext);
  if (!context) {
    throw new Error('useSwarmStream must be used within a SwarmProvider');
  }
  return context;
};
