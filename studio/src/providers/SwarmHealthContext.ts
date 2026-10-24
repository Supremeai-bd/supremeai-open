import { createContext } from 'react';
// বাংলা মন্তব্য: প্রপার আপেক্ষিক পাথ ../types/swarm ইম্পোর্ট ঠিক করা হলো
import type { SwarmContextState } from '../types/swarm';

// বাংলা মন্তব্য: SwarmHealthContext এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে MockSwarmProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export const SwarmHealthContext = createContext<SwarmContextState | null>(null);
