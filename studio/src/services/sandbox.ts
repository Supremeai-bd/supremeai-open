import type { WebContainer } from '@webcontainer/api';

export interface SandboxExecutionResult {
  status: 'SUCCESS' | 'FAILED' | 'TIMEOUT';
  stdout: string;
  stderr: string;
  executionTimeMs: number;
}

export class SandboxService {
  private timeoutMs: number;
  private containerInstance: WebContainer | null = null;
  private isInitializing: boolean = false;

  constructor(timeoutMs: number = 10000) {
    this.timeoutMs = timeoutMs;
  }

  async initialize() {
    if (this.containerInstance) return;
    if (this.isInitializing) {
      // Wait for initialization to complete
      while (this.isInitializing) {
        await new Promise(r => setTimeout(r, 100));
      }
      return;
    }

    this.isInitializing = true;
    console.warn('Booting WebContainer...');
    try {
      const { WebContainer } = await import('@webcontainer/api');
      this.containerInstance = await WebContainer.boot();
      console.warn('WebContainer booted successfully.');
    } catch (e) {
      console.error('Failed to boot WebContainer:', e);
      throw e;
    } finally {
      this.isInitializing = false;
    }
  }

  /**
   * Executes a command within the WebContainer with strict timeout enforcement.
   */
  async executeCommand(command: string, args: string[]): Promise<SandboxExecutionResult> {
    await this.initialize();

    if (!this.containerInstance) {
      throw new Error('WebContainer is not initialized');
    }

    console.warn(`Executing in Sandbox: ${command} ${args.join(' ')} (Timeout: ${this.timeoutMs}ms)`);

    const startTime = Date.now();
    let stdout = '';
    const stderr = '';

    return new Promise((resolve) => {
      let isResolved = false;

      const timer = setTimeout(() => {
        if (!isResolved) {
          isResolved = true;
          resolve({
            status: 'TIMEOUT',
            stdout,
            stderr: stderr + '\n[TIMEOUT] Execution exceeded timeout limits to prevent infinite loop.',
            executionTimeMs: Date.now() - startTime,
          });
        }
      }, this.timeoutMs);

      (async () => {
        try {
          const process = await this.containerInstance!.spawn(command, args);

          process.output.pipeTo(
            new WritableStream({
              write(data) {
                stdout += data;
              },
            })
          );

          const exitCode = await process.exit;

          if (!isResolved) {
            isResolved = true;
            clearTimeout(timer);
            resolve({
              status: exitCode === 0 ? 'SUCCESS' : 'FAILED',
              stdout,
              stderr,
              executionTimeMs: Date.now() - startTime,
            });
          }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } catch (err: any) {
          if (!isResolved) {
            isResolved = true;
            clearTimeout(timer);
            resolve({
            status: 'FAILED',
            stdout,
            stderr: err.toString(),
            executionTimeMs: Date.now() - startTime,
          });
        }
      }
      })();
    });
  }
}

export const sandboxService = new SandboxService();
