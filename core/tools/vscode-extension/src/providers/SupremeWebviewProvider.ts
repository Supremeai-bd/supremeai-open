import * as vscode from 'vscode';
import axios from 'axios';
export class SupremeWebviewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'supremeai.sidebarViews';
    constructor(private readonly _extensionUri: vscode.Uri) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken,
    ) {
        webviewView.webview.options = {
            enableScripts: true, // স্ক্রিপ্ট এক্সিকিউশন এনাবল করা
            localResourceRoots: [this._extensionUri]
        };
        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

        // 📡 IPC মেসেজ লিসেনার
        this._setupMessageListener(webviewView.webview);

        // resolveWebviewView মেথডের ভেতরে HTML রেন্ডার হওয়ার ঠিক নিচে যোগ করা হলো:
        this._fetchLiveRecipes().then(recipes => {
            webviewView.webview.postMessage({
                command: 'hydrateRecipes',
                data: recipes
            });
        });
    }

    private async _fetchLiveRecipes(): Promise<any[]> {
        try {
            // আমাদের স্ট্রেস টেস্টে গ্রিন প্রমাণিত হওয়া ব্যাকএন্ড এন্ডপয়েন্ট
            const backendUrl = 'https://supremeai-api-lhlwyikwlq-uc.a.run.app/api/skills';
            // AuthService থেকে বর্তমান টোকেন ব্যবহার করা হলো (হার্ডকোডেড টোকেন নয়)
            const { AuthService } = require('../services/AuthService');
            const authService = AuthService.getInstance();
            const token = authService?.getToken();
            const headers: Record<string, string> = {};
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            const response = await axios.get(backendUrl, { headers });

            if (response.status === 200 && response.data) {
                return response.data.skills || response.data; // ডিবি স্কিল অ্যারে
            }
            return [];
        } catch (error) {
            console.error('🔴 Failed to fetch live skills for VS Code Sidebar:', error);
            return [];
        }
    }

    private _getHtmlForWebview(webview: vscode.Webview): string {
        const nonce = this.getNonce();
        return `
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
                <style>
                    body { font-family: sans-serif; padding: 10px; color: var(--vscode-foreground); }
                    .recipe-card { background: var(--vscode-button-secondaryBackground); padding: 8px; margin-bottom: 8px; border-radius: 4px; border: 1px solid var(--vscode-widget-border); }
                    .btn { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; cursor: pointer; width: 100%; border-radius: 2px; }
                    .btn:hover { background: var(--vscode-button-hoverBackground); }
                    h4 { margin: 0 0 6px 0; color: var(--vscode-textLink-foreground); }
                </style>
            </head>
            <body>
                <h3>SupremeAI Recipe Factory</h3>
                <div id="recipe-container">Loading dynamic skills...</div>

                <script nonce="${nonce}">
                    const vscode = acquireVsCodeApi();
                    const container = document.getElementById('recipe-container');

                    // 📡 এক্সটেনশন থেকে আসা ডাটা শোনার লিসেনার
                    window.addEventListener('message', event => {
                        const message = event.data;
                        if (message.command === 'hydrateRecipes') {
                            const recipes = message.data;
                            if (!recipes || recipes.length === 0) {
                                container.replaceChildren();
                                const empty = document.createElement('p');
                                empty.textContent = 'No active automation recipes found.';
                                container.appendChild(empty);
                                return;
                            }

                            container.replaceChildren();
                            recipes.forEach(recipe => {
                                const card = document.createElement('div');
                                card.className = 'recipe-card';
                                
                                const title = document.createElement('h4');
                                title.textContent = recipe.skill_name;
                                card.appendChild(title);
                                
                                const desc = document.createElement('p');
                                desc.style.fontSize = '11px';
                                desc.style.margin = '0 0 8px 0';
                                desc.textContent = recipe.description || '';
                                card.appendChild(desc);
                                
                                const btn = document.createElement('button');
                                btn.className = 'btn';
                                btn.textContent = 'Execute Automation';
                                btn.addEventListener('click', () => triggerRecipe(recipe.skill_name));
                                card.appendChild(btn);

                                container.appendChild(card);
                            });
                        }
                    });

                    function triggerRecipe(name) {
                        vscode.postMessage({
                            command: 'executeLocalRecipe',
                            recipeName: name
                        });
                    }
                </script>
            </body>
            </html>
        `;
    }

    private getNonce() {
        let text = '';
        const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        for (let i = 0; i < 32; i++) {
            text += possible.charAt(Math.floor(Math.random() * possible.length));
        }
        return text;
    }

    private _setupMessageListener(webview: vscode.Webview) {
        webview.onDidReceiveMessage(async (message) => {
            switch (message.command) {
                case 'executeLocalRecipe':
                    // আমাদের সদ্য ফিক্স করা ক্লাউড রান ব্যাকএন্ড এপিআই-তে টাস্ক পুশ করবে
                    vscode.window.showInformationMessage(`🚀 Triggering Recipe: ${message.recipeName}`);
                    break;
                case 'showError':
                    vscode.window.showErrorMessage(`🔴 Webview Error: ${message.text}`);
                    break;
            }
        });
    }
}

