// Issue #2475: আগের বাস্তবায়নটি /admin/microservices/java-worker/health endpoint-কে
// কল করত, যা backend-এ (openapi.json + FastAPI routers) কখনোই ছিল না — প্রতিটি
// কল নীরব 404 দিত এবং catch-ব্লক সেটিকে OFFLINE-এ রূপান্তর করত। Java worker
// microservice-এর কোনো proxy route এখনো বাস্তবায়িত হয়নি, তাই সৎ (honest)
// আচরণ হলো নেটওয়ার্ক কল না করে সরাসরি OFFLINE রিটার্ন করা — একই UI ফলাফল,
// কিন্তু অপচয়ায়িত round-trip ও console noise নেই। যখন আসল endpoint যোগ হবে,
// তখন এখানে আবার apiClient কল ফিরিয়ে আনতে হবে।

export interface JavaWorkerHealth {
  status: string;
  uptimeSeconds: number;
  activeTasks: number;
  queuedTasks: number;
  memoryUsageMb: number;
  cpuLoadPercentage: number;
  totalTasksProcessed: number;
}

const OFFLINE: JavaWorkerHealth = {
  status: 'OFFLINE',
  uptimeSeconds: 0,
  activeTasks: 0,
  queuedTasks: 0,
  memoryUsageMb: 0,
  cpuLoadPercentage: 0,
  totalTasksProcessed: 0,
};

export const fetchJavaWorkerHealth = async (): Promise<JavaWorkerHealth> => {
  // Java worker health endpoint এখনো backend-এ নেই (issue #2475) —
  // সরাসরি OFFLINE রিপোর্ট; কোনো নীরব 404 রিকোয়েস্ট আর যাবে না।
  // Fresh copy ফেরানো হচ্ছে যাতে কোনো caller-এর mutation পরের কলে লিক না করে।
  return { ...OFFLINE };
};
