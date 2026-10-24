/**
 * Terminal Activity Sensor for SupremeAI VS Code Extension.
 *
 * Monitors integrated terminals and active execution processes (e.g. npm, pytest, docker)
 * to instantly halt background tasks and ensure absolute Zero-Lag user experience.
 */

import * as vscode from 'vscode';

export class TerminalActivitySensor {
  private static instance: TerminalActivitySensor;
  private isTerminalActive: boolean = false;
  private activeTerminalCount: number = 0;
  private disposables: vscode.Disposable[] = [];

  private constructor() {
    this.initListeners();
  }

  public static getInstance(): TerminalActivitySensor {
    if (!TerminalActivitySensor.instance) {
      TerminalActivitySensor.instance = new TerminalActivitySensor();
    }
    return TerminalActivitySensor.instance;
  }

  private initListeners(): void {
    // 1. Listen to active terminal state changes
    this.disposables.push(
      vscode.window.onDidChangeActiveTerminal((terminal) => {
        this.updateState();
      })
    );

    // 2. Listen to terminal open / close events
    this.disposables.push(
      vscode.window.onDidOpenTerminal((terminal) => {
        this.updateState();
      }),
      vscode.window.onDidCloseTerminal((terminal) => {
        this.updateState();
      })
    );

    // Initial check
    this.updateState();
  }

  private updateState(): void {
    const terminals = vscode.window.terminals;
    this.activeTerminalCount = terminals.length;
    
    // Check if any terminal is currently open or focused
    this.isTerminalActive = this.activeTerminalCount > 0;
  }

  /**
   * Returns true if any active terminal process is running or open, indicating background tasks should pause.
   */
  public shouldPauseBackgroundTasks(): boolean {
    return this.isTerminalActive || vscode.window.terminals.length > 0;
  }

  public getActiveTerminalCount(): number {
    return this.activeTerminalCount;
  }

  public dispose(): void {
    this.disposables.forEach((d) => d.dispose());
  }
}

export const terminalSensor = TerminalActivitySensor.getInstance();
