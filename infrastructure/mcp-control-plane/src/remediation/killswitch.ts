export class KillSwitchManager {
  private autonomyEnabled: boolean = true;

  public isAutonomyEnabled(): boolean {
    return this.autonomyEnabled;
  }

  public emergencyStop(): void {
    if (!this.autonomyEnabled) return;
    
    this.autonomyEnabled = false;
    console.error(`[KILL SWITCH] 🚨 AUTONOMY DISABLED. Dropping to L0 (Read-Only) Mode.`);
    
    // Stop the background task scheduler if it's running
    import("../tasks/engine.js").then(({ globalTaskEngine }) => {
       globalTaskEngine.stopBackgroundScheduler();
       // Note: We don't forcefully kill running tasks right now, 
       // but we could mark them as failed or cancel them if we had cancellation tokens.
       console.error(`[KILL SWITCH] Background task scheduler stopped.`);
    }).catch(console.error);
  }

  public enableAutonomy(): void {
    if (this.autonomyEnabled) return;

    this.autonomyEnabled = true;
    console.log(`[KILL SWITCH] ✅ AUTONOMY RE-ENABLED.`);
  }
}

export const globalKillSwitch = new KillSwitchManager();
