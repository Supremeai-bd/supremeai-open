export const AppDefaults = {  // 🔧 DYNAMIC: All values from env or backend /api/config/public
  adminEmail: import.meta.env.VITE_DEFAULT_ADMIN_EMAIL || '',
  maxConcurrency: parseInt(import.meta.env.VITE_MAX_CONCURRENCY || '3', 10),
  features: {
    // বাংলা মন্তব্য: ব্যাকএন্ড public_config.py safe-default (selfHealing: true) এর সাথে মিল রাখা হয়েছে।
    // শুধু তখনই ব্যবহার হয় যখন /api/config/public fetch ব্যর্থ (offline/network-down)।
    // self-healing ইঞ্জিন bounded retry (max N + backoff) ধরে নেওয়া হচ্ছে যাতে ইনফিনিট লুপ না হয়।
    selfHealing: import.meta.env.VITE_SELF_HEALING !== 'false',  // 🔧 DYNAMIC
    costGuard: import.meta.env.VITE_COST_GUARD !== 'false'  // 🔧 DYNAMIC
  }
};
