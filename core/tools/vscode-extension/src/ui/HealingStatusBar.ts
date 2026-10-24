import * as vscode from 'vscode';
import { HealingStateManager, HealingState } from '@supremeai/shared-services';

export class HealingStatusBar {
    private statusBarItem: vscode.StatusBarItem;

    constructor(context: vscode.ExtensionContext) {
        // Right alignment, priority 100 (Language indicator-এর ঠিক পাশেই থাকবে)
        this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        context.subscriptions.push(this.statusBarItem);

        // Subscribe to State Machine
        HealingStateManager.getInstance().onDidChangeState((event) => {
            this.update(event.state, event.message);
        });

        this.update(HealingState.IDLE);
    }

    private update(state: HealingState, message?: string) {
        switch (state) {
            case HealingState.IDLE:
                this.statusBarItem.text = '$(shield) SupremeAI';
                this.statusBarItem.tooltip = 'SupremeAI Agent is active';
                this.statusBarItem.show();
                break;
            case HealingState.ANALYZING_ERROR:
                this.statusBarItem.text = '$(sync~spin) SupremeAI: Analyzing...';
                this.statusBarItem.tooltip = 'Extracting Semantic Context';
                this.statusBarItem.show();
                break;
            case HealingState.GENERATING_PATCH:
                this.statusBarItem.text = '$(loading~spin) SupremeAI: Healing...';
                this.statusBarItem.tooltip = 'Generating fix from Swarm Orchestrator';
                this.statusBarItem.show();
                break;
            case HealingState.APPLYING_DIFF:
                this.statusBarItem.text = '$(diff-editor) SupremeAI: Diff Ready';
                this.statusBarItem.tooltip = 'Review the proposed fix';
                this.statusBarItem.show();
                break;
            case HealingState.SUCCESS:
                this.statusBarItem.text = '$(check) SupremeAI: Healed';
                setTimeout(() => this.update(HealingState.IDLE), 3000); // 3 সেকেন্ড পর IDLE-এ ফিরে যাবে
                break;
            case HealingState.FAILED:
                this.statusBarItem.text = '$(error) SupremeAI: Failed';
                this.statusBarItem.tooltip = message || 'Healing failed';
                setTimeout(() => this.update(HealingState.IDLE), 5000);
                break;
        }
    }
}
