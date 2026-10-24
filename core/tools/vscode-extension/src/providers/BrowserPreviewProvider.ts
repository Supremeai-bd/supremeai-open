import * as vscode from 'vscode';

export class BrowserPreviewProvider {
  private static currentPanel: vscode.WebviewPanel | undefined;

  public static createOrShow(context: vscode.ExtensionContext, title: string, sessionId: string): vscode.WebviewPanel {
    if (BrowserPreviewProvider.currentPanel) {
      BrowserPreviewProvider.currentPanel.dispose();
    }

    const panel = vscode.window.createWebviewPanel(
      'supremeaiBrowserPreview',
      title,
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    BrowserPreviewProvider.currentPanel = panel;
    panel.webview.html = BrowserPreviewProvider.getWebviewContent(sessionId);

    panel.webview.onDidReceiveMessage(
      message => {
        switch (message.command) {
          case 'stop':
            vscode.window.showInformationMessage(`ব্রাউজার টাস্ক ${sessionId} বন্ধ করা হচ্ছে।`);
            return;
          case 'pause':
            vscode.window.showInformationMessage(`ব্রাউজার টাস্ক ${sessionId} পজ করা হচ্ছে।`);
            return;
          case 'resume':
            vscode.window.showInformationMessage(`ব্রাউজার টাস্ক ${sessionId} চালু করা হচ্ছে।`);
            return;
          case 'taskCompleteNotification':
            vscode.window.showInformationMessage('ব্রাউজার টাস্ক সম্পন্ন হয়েছে!');
            return;
        }
      },
      undefined,
      context.subscriptions
    );

    panel.onDidDispose(() => {
      BrowserPreviewProvider.currentPanel = undefined;
    }, null, context.subscriptions);

    return panel;
  }

  private static getWebviewContent(sessionId: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https: vscode-webview-resource:; script-src 'unsafe-inline' 'unsafe-eval' https: vscode-webview-resource:; img-src 'self' data: https: vscode-webview-resource:;">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SupremeAI ব্রাউজার প্রিভিউ</title>
    <style>
        body { font-family: sans-serif; margin: 0; padding: 10px; background-color: var(--vscode-editor-background); color: var(--vscode-editor-foreground); }
        #controls { margin-bottom: 10px; display: flex; gap: 10px; }
        #previewContainer { position: relative; display: inline-block; }
        #previewImage { max-width: 100%; height: auto; border: 1px solid var(--vscode-editorGroup-border); cursor: crosshair; }
        #logOutput { background-color: var(--vscode-editorWidget-background); border: 1px solid var(--vscode-editorGroup-border); padding: 10px; max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.9em; }
        button { background-color: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 8px 12px; cursor: pointer; border-radius: 3px; }
        button:hover { background-color: var(--vscode-button-hoverBackground); }
        #interactionBox { margin-top: 10px; padding: 10px; background: rgba(255,255,255,0.1); border-radius: 5px; display: none; }
        #interactionBox.active { display: block; border: 2px solid var(--vscode-button-background); }
        input { background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); padding: 5px; width: 70%; }
    </style>
</head>
<body>
    <h1>Godmode 3 লাইভ প্রিভিউ (Session: ${sessionId})</h1>
    <div id="controls">
        <button id="stopButton">বন্ধ করুন</button>
        <button id="pauseButton">পজ করুন</button>
        <button id="resumeButton">চালু করুন</button>
    </div>
    <div id="previewContainer">
        <img id="previewImage" src="" alt="লাইভ ব্রাউজার প্রিভিউ" />
    </div>
    <div id="interactionBox">
        <p id="promptText">AI আপনার সাহায্য চাইছে...</p>
        <input type="text" id="userInput" placeholder="এখানে ইনপুট দিন..." />
        <button id="sendInput">পাঠান</button>
    </div>
    <h2>লগ আউটপুট</h2>
    <div id="logOutput"></div>

    <script>
        const vscode = acquireVsCodeApi();
        const previewImage = document.getElementById('previewImage');
        const logOutput = document.getElementById('logOutput');
        const stopButton = document.getElementById('stopButton');
        const pauseButton = document.getElementById('pauseButton');
        const resumeButton = document.getElementById('resumeButton');
        const interactionBox = document.getElementById('interactionBox');
        const userInput = document.getElementById('userInput');
        const sendInput = document.getElementById('sendInput');
        const promptText = document.getElementById('promptText');

        stopButton.addEventListener('click', () => {
            vscode.postMessage({ command: 'stop', sessionId: '${sessionId}' });
        });
        pauseButton.addEventListener('click', () => {
            vscode.postMessage({ command: 'pause', sessionId: '${sessionId}' });
        });
        resumeButton.addEventListener('click', () => {
            vscode.postMessage({ command: 'resume', sessionId: '${sessionId}' });
        });

        previewImage.addEventListener('click', (e) => {
            const rect = previewImage.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width;
            const y = (e.clientY - rect.top) / rect.height;
            vscode.postMessage({ command: 'click', sessionId: '${sessionId}', x, y });
        });

        sendInput.addEventListener('click', () => {
            const text = userInput.value;
            if (text) {
                vscode.postMessage({ command: 'userInput', sessionId: '${sessionId}', text });
                userInput.value = '';
                interactionBox.classList.remove('active');
            }
        });

        window.addEventListener('message', event => {
            const message = event.data;
            switch (message.type) {
                case 'updateImage':
                    previewImage.src = 'data:image/png;base64,' + message.data;
                    break;
                case 'updateLog': {
                    const logEntry = document.createElement('p');
                    logEntry.textContent = message.data;
                    logOutput.appendChild(logEntry);
                    logOutput.scrollTop = logOutput.scrollHeight;
                    break;
                }
                case 'askUser':
                    promptText.innerText = message.data;
                    interactionBox.classList.add('active');
                    userInput.focus();
                    break;
                case 'taskComplete': {
                    const taskEntry = document.createElement('p');
                    const taskLabel = document.createElement('b');
                    taskLabel.textContent = 'টাস্ক সম্পন্ন হয়েছে:';
                    taskEntry.appendChild(taskLabel);
                    taskEntry.appendChild(document.createTextNode(' ' + message.result));
                    logOutput.appendChild(taskEntry);
                    // vscode.window webview-এ সংজ্ঞায়িত নয় — postMessage দিয়ে extension-কে জানানো হবে
                    vscode.postMessage({ command: 'taskCompleteNotification' });
                    break;
                }
            }
        });
    </script>
</body>
</html>`;
  }
}



