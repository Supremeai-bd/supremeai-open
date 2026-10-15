import * as crypto from "node:crypto";
import { globalHealthEngine } from "../health/engine.js";

export type TaskState = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";

export interface Task {
  id: string;
  name: string;
  state: TaskState;
  createdAt: string;
  updatedAt: string;
  error?: string;
}

export class TaskEngine {
  private tasks = new Map<string, Task>();
  private backgroundInterval?: NodeJS.Timeout;

  /**
   * Registers and starts a new async task.
   */
  public async runTask(name: string, fn: () => Promise<void>): Promise<string> {
    const id = `TSK-${crypto.randomUUID().substring(0, 8)}`;
    const now = new Date().toISOString();
    
    const task: Task = {
      id,
      name,
      state: "RUNNING",
      createdAt: now,
      updatedAt: now,
    };
    this.tasks.set(id, task);

    console.log(`[TASK] Started: ${name} (${id})`);

    // Run async without blocking
    Promise.resolve(fn())
      .then(() => {
        task.state = "SUCCEEDED";
        task.updatedAt = new Date().toISOString();
        this.tasks.set(id, task);
        console.log(`[TASK] Succeeded: ${name} (${id})`);
      })
      .catch((err) => {
        task.state = "FAILED";
        task.error = err.message;
        task.updatedAt = new Date().toISOString();
        this.tasks.set(id, task);
        console.error(`[TASK] Failed: ${name} (${id}) - ${err.message}`);
      });

    return id;
  }

  /**
   * Starts a background scheduler (e.g. cron).
   */
  public startBackgroundScheduler(intervalMs: number = 5 * 60 * 1000): void {
    if (this.backgroundInterval) {
      clearInterval(this.backgroundInterval);
    }
    console.log(`[TASK] Background Scheduler started (Interval: ${intervalMs}ms)`);
    
    this.backgroundInterval = setInterval(() => {
      this.runTask("System Health Sweep", async () => {
        console.log(`[SCHEDULER] Triggering background health sweep...`);
        await globalHealthEngine.runFullSweep();
      });
    }, intervalMs);
  }

  public stopBackgroundScheduler(): void {
    if (this.backgroundInterval) {
      clearInterval(this.backgroundInterval);
      this.backgroundInterval = undefined;
      console.log(`[TASK] Background Scheduler stopped.`);
    }
  }

  public getTasks(): Task[] {
    return Array.from(this.tasks.values());
  }
}

export const globalTaskEngine = new TaskEngine();
