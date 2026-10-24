import { ChatMessage } from '../types';

/**
 * SupremeAIChatView - Generates the HTML templates for the Chat Webview.
 */
export class SupremeAIChatView {
  /**
   * Returns the login view HTML.
   */
  public static getLoginHTML(): string {
    return `<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline' https: vscode-webview-resource:; script-src 'unsafe-inline' 'unsafe-eval' https: vscode-webview-resource:; img-src 'self' data: https: vscode-webview-resource:;">
  <style>
    body {
      font-family: var(--vscode-font-family);
      padding: 20px;
      color: var(--vscode-foreground);
      background-color: var(--vscode-sideBar-background);
      text-align: center;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      height: 80vh;
    }
    .logo { font-size: 50px; margin-bottom: 20px; }
    .title { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
    .desc { font-size: 13px; color: var(--vscode-descriptionForeground); margin-bottom: 24px; line-height: 1.5; }
    .btn {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      padding: 10px 20px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      font-weight: bold;
      width: 100%;
      max-width: 200px;
    }
    .btn:hover { background: var(--vscode-button-hoverBackground); }
  </style>
</head>
<body>
  <div class="logo">🤖</div>
  <div class="title">SupremeAI-তে লগইন করুন</div>
  <div class="desc">আপনার কোড অ্যাসিস্ট্যান্ট ব্যবহার করতে এবং চ্যাট ইন্টারফেসে চ্যাট করতে সাইন-ইন করা প্রয়োজন।</div>
  <button class="btn" id="loginBtn">লগইন করুন</button>
  <button class="btn btn-secondary" id="guestBtn" style="margin-top: 10px; background: var(--vscode-button-secondaryBackground, #3a3d41); color: var(--vscode-button-secondaryForeground, #ffffff);">গেস্ট হিসেবে ব্যবহার করুন</button>

  <script>
    const vscode = acquireVsCodeApi();
    const abortController = new AbortController();
    window.addEventListener("unload", () => abortController.abort());
    document.getElementById('loginBtn').addEventListener('click', () => { vscode.postMessage({ type: 'login' }, { signal: abortController.signal }); });
    document.getElementById('guestBtn').addEventListener('click', () => { vscode.postMessage({ type: 'loginAsGuest' }, { signal: abortController.signal }); });
  </script>
</body>
</html>`;
  }

  /**
   * Returns the main chat interface HTML.
   */
  private static escapeHtml(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  public static getHTMLContent(isGuest: boolean, username: string, hasApiKey: boolean, messageHistory: ChatMessage[]): string {
    const safeUsername = this.escapeHtml(username || 'User');
    const messagesHtml = (messageHistory || []).map(msg => this.renderMessage(msg)).join('');
    const emptyState = (!messageHistory || messageHistory.length === 0) ? this.getEmptyState(safeUsername) : '';

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: var(--vscode-font-family); background: var(--vscode-sideBar-background); color: var(--vscode-foreground); height: 100vh; display: flex; flex-direction: column; }
    .header { padding: 12px 16px; border-bottom: 1px solid var(--vscode-panel-border); display: flex; align-items: center; justify-content: space-between; background: var(--vscode-sideBarSectionHeader-background); }
    .header h2 { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
    .header-actions { display: flex; gap: 8px; }
    .btn { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; }
    .btn:hover { background: var(--vscode-button-hoverBackground); }
    .btn-secondary { background: var(--vscode-toolbar-hoverBackground); color: var(--vscode-foreground); }
    .messages { flex: 1; overflow-y: auto; padding: 16px; }
    .empty-state { text-align: center; padding: 60px 20px; color: var(--vscode-descriptionForeground); }
    .empty-state-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.5; }
    .empty-state h3 { font-size: 16px; margin-bottom: 8px; color: var(--vscode-foreground); }
    .empty-state p { font-size: 13px; line-height: 1.5; }
    .quick-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; justify-content: center; }
    .quick-btn { background: var(--vscode-list-hoverBackground); border: 1px solid var(--vscode-panel-border); color: var(--vscode-foreground); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 12px; }
    .quick-btn:hover { background: var(--vscode-list-activeSelectionBackground); border-color: var(--vscode-focusBorder); }
    .input-area { padding: 12px 16px; border-top: 1px solid var(--vscode-panel-border); background: var(--vscode-sideBar-background); }
    .input-wrapper { display: flex; gap: 8px; align-items: flex-end; }
    textarea { flex: 1; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); border-radius: 6px; padding: 10px 12px; font-family: var(--vscode-font-family); font-size: 13px; resize: none; min-height: 40px; max-height: 120px; }
    textarea:focus { outline: none; border-color: var(--vscode-focusBorder); }
    .send-btn { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; }
    .send-btn:hover { background: var(--vscode-button-hoverBackground); }
    .message { display: flex; gap: 12px; margin-bottom: 16px; animation: slideIn 0.3s ease; }
    @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .message.user { flex-direction: row-reverse; }
    .avatar { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; margin-top: 4px; }
    .avatar.user-avatar { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
    .avatar.ai-avatar { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; }
    .message-content { flex: 1; padding: 12px 16px; border-radius: 12px; font-size: 13px; line-height: 1.6; word-wrap: break-word; }
    .user .message-content { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border-bottom-right-radius: 4px; }
    .assistant .message-content { background: var(--vscode-list-hoverBackground); color: var(--vscode-foreground); border-bottom-left-radius: 4px; }
    .message-content.error { background: var(--vscode-errorBackground); color: var(--vscode-errorForeground); }
    .message-meta { font-size: 11px; color: var(--vscode-descriptionForeground); margin-top: 4px; }
    .thinking { opacity: 0.7; }
    .thinking::after { content: '...'; animation: dots 1.5s infinite; }
    @keyframes dots { 0%, 20% { content: ''; } 40% { content: '.'; } 60%, 100% { content: '...'; } }
  </style>
</head>
<body>
  <div class="header">
    <h2>🤖 SupremeAI (${safeUsername})</h2>
    <div class="header-actions">
      ${isGuest ? '<button class="btn" onclick="login()">Login</button>' : '<button class="btn btn-secondary" onclick="logout()">Logout</button>'}
      <button class="btn btn-secondary" onclick="newChat()">New Chat</button>
      <button class="btn btn-secondary" onclick="clearChat()">Clear</button>
      <button class="btn btn-secondary" onclick="openSettings()">⚙️</button>
    </div>
  </div>
  ${isGuest ? '' : `
  <div style="padding: 6px 16px; font-size: 11px; background: var(--vscode-input-background, #1e1e1e); border-bottom: 1px solid var(--vscode-panel-border); color: var(--vscode-descriptionForeground); display: flex; justify-content: space-between; align-items: center;">
    <span>🔑 API Key:</span>
    <span style="font-weight: bold; color: ${hasApiKey ? 'var(--vscode-testing-iconPassedColor, #73c991)' : 'var(--vscode-testing-iconFailedColor, #f14c4c)'};">
      ${hasApiKey ? 'Active' : 'Missing'}
    </span>
  </div>
  `}
  <div class="messages" id="messages">
    ${emptyState}
    ${messagesHtml}
  </div>
  <div class="input-area">
    <div class="input-wrapper">
      <textarea id="messageInput" placeholder="Ask SupremeAI..." rows="1" onkeydown="handleKeydown(event)" oninput="autoResize(this)"></textarea>
      <button class="send-btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
    <div class="quick-actions">
      <button class="quick-btn" onclick="quickAction('explain')">📄 Explain</button>
      <button class="quick-btn" onclick="quickAction('fix')">🐛 Fix</button>
      <button class="quick-btn" onclick="quickAction('refactor')">🔄 Refactor</button>
      <button class="quick-btn" onclick="quickAction('review')">👀 Review</button>
    </div>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const abortController = new AbortController();
    window.addEventListener("unload", () => abortController.abort());
    const messagesDiv = document.getElementById('messages');
    let currentStreamingEl: HTMLElement | null = null;
    const escapeHtml = (value) => {
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    };

    const appendMessageElement = (element) => {
      messagesDiv.appendChild(element);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    };

    window.addEventListener('message', event => {
      const data = event.data;
      if (data.type === 'addMessage' || data.type === 'showThinking') {
        const msgData = data.type === 'addMessage' ? data.message : { id: 'thinking', role: 'assistant', content: '🤔 Thinking...', timestamp: new Date().toISOString(), thinking: true };
        if (data.type === 'showThinking') {
          const existing = document.getElementById('thinking-message-container');
          if (existing) existing.remove();
        }
        const msgElement = renderMessage(msgData);
        const emptyState = document.querySelector('.empty-state');
        if (emptyState) emptyState.remove();
        appendMessageElement(msgElement);
      } else if (data.type === 'removeThinking') {
        const indicators = document.querySelectorAll('[id="thinking-message-container"]');
        indicators.forEach(el => el.remove());
      } else if (data.type === 'streamChunk') {
        const text = data.text || '';
        if (!currentStreamingEl) {
          const thinkingMsg = { id: 'streaming', role: 'assistant', content: text, timestamp: new Date().toISOString(), thinking: false };
          const msgElement = renderMessage(thinkingMsg);
          appendMessageElement(msgElement);
          currentStreamingEl = document.getElementById('thinking-message-container');
          if (currentStreamingEl) currentStreamingEl.removeAttribute('id');
          const aiContentEl = currentStreamingEl ? currentStreamingEl.querySelector('.message-content') : null;
          if (aiContentEl) aiContentEl.classList.remove('thinking');
          const emptyState = document.querySelector('.empty-state');
          if (emptyState) emptyState.remove();
        } else {
          const aiContentEl = currentStreamingEl.querySelector('.message-content');
          if (aiContentEl) {
            aiContentEl.textContent += text;
          }
        }
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
      } else if (data.type === 'streamEnd') {
        if (currentStreamingEl) {
          const aiContentEl = currentStreamingEl.querySelector('.message-content');
          if (aiContentEl) aiContentEl.classList.remove('thinking');
          currentStreamingEl = null;
        }
      }
    }, { signal: abortController.signal });
    function renderMessage(msg) {
      const time = new Date(msg.timestamp || Date.now()).toLocaleTimeString();
      const role = msg.role || 'assistant';
      const isThinking = msg.thinking;

      const container = document.createElement('div');
      container.className = 'message-container';
      if (isThinking) {
        container.id = 'thinking-message-container';
      }

      const messageDiv = document.createElement('div');
      messageDiv.className = 'message ' + role;

      const avatar = document.createElement('div');
      avatar.className = 'avatar ' + role + '-avatar';
      avatar.textContent = role === 'user' ? 'U' : 'AI';

      const contentDiv = document.createElement('div');
      contentDiv.className = 'message-content ' + (msg.error ? 'error' : '') + ' ' + (isThinking ? 'thinking' : '');
      contentDiv.textContent = msg.content || '';

      const metaDiv = document.createElement('div');
      metaDiv.className = 'message-meta';
      metaDiv.style.marginLeft = role === 'user' ? 'auto' : '44px';
      metaDiv.style.textAlign = role === 'user' ? 'right' : 'left';
      metaDiv.textContent = time;

      messageDiv.appendChild(avatar);
      messageDiv.appendChild(contentDiv);
      container.appendChild(messageDiv);
      container.appendChild(metaDiv);

      return container;
    }
    function sendMessage() {
      const input = document.getElementById('messageInput');
      const message = input.value.trim();
      if (!message) return;
      vscode.postMessage({ type: 'sendMessage', message: message });
      input.value = '';
      input.style.height = '40px';
    }
    function handleKeydown(event) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); } }
    function autoResize(textarea) { textarea.style.height = 'auto'; textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px'; }
    function newChat() { vscode.postMessage({ type: 'newChat' }); }
    function clearChat() { vscode.postMessage({ type: 'clearChat' }); }
    function openSettings() { vscode.postMessage({ type: 'openSettings' }); }
    function login() { vscode.postMessage({ type: 'login' }); }
    function logout() { vscode.postMessage({ type: 'logout' }); }
    function quickAction(action) { vscode.postMessage({ type: action === 'review' ? 'sendMessage' : action + 'Code', message: action === 'explain' ? 'Please explain this code' : action === 'fix' ? 'Please help fix this code' : action === 'refactor' ? 'Please suggest improvements for this code' : 'Please review this code and suggest improvements' }); }
  </script>
</body>
</html>`;
  }

  /**
   * Renders a single message for the initial server-side load.
   */
  public static renderMessage(msg: ChatMessage): string {
    let time = '';
    try {
      time = new Date(msg.timestamp).toLocaleTimeString();
    } catch (e) {
      time = new Date().toLocaleTimeString();
    }

    const isThinking = msg.thinking;
    const isError = msg.error;
    const role = msg.role || 'assistant';
    const content = this.escapeHtml(msg.content || '');

    return `
      <div class="message-container" ${isThinking ? 'id="thinking-message-container"' : ''}>
        <div class="message ${role}">
          <div class="avatar ${role}-avatar">
            ${role === 'user' ? 'U' : 'AI'}
          </div>
          <div class="message-content ${isError ? 'error' : ''} ${isThinking ? 'thinking' : ''}">
            ${content}
          </div>
        </div>
        <div class="message-meta" style="margin-left: ${role === 'user' ? 'auto' : '44px'}; text-align: ${role === 'user' ? 'right' : 'left'};">
          ${time}
        </div>
      </div>
    `;
  }

  private static getEmptyState(username: string): string {
    const welcomeMsg = 'Your intelligent coding companion is ready to help!';
    const quickActions = [
      { icon: '📄', label: 'Explain Code', action: 'explain' },
      { icon: '🐛', label: 'Fix Code', action: 'fix' },
      { icon: '🔄', label: 'Refactor', action: 'refactor' },
      { icon: '👀', label: 'Review', action: 'review' }
    ];

    return `
      <div class="empty-state">
        <div class="empty-state-icon">🤖</div>
        <h3>Welcome, ${username}</h3>
        <p>${welcomeMsg}</p>
        <div class="quick-actions">
          ${quickActions.map(a => '<button class="quick-btn" onclick="quickAction(\'' + a.action + '\')">' + a.icon + ' ' + a.label + '</button>').join('')}
        </div>
      </div>
    `;
  }
}




