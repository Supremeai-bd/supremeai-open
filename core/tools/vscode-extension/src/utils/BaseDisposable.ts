import * as vscode from 'vscode';

export abstract class BaseDisposable implements vscode.Disposable {
    protected disposables: vscode.Disposable[] = [];

    protected register<T extends vscode.Disposable>(disposable: T): T {
        this.disposables.push(disposable);
        return disposable;
    }

    public dispose(): void {
        while (this.disposables.length) {
            const item = this.disposables.pop();
            if (item) {
                item.dispose();
            }
        }
    }
}
