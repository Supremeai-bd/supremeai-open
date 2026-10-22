# SupremeAI Unified Client Hub (`supremeai-vscode`)

Native client applications and developer workflows for SupremeAI.  
Per [`ARCHITECTURE_PLAN.md`](https://github.com/Supremeai-bd/supremeai-open/blob/main/ARCHITECTURE_PLAN.md), this repository hosts all non-cloud client applications:

| Subdirectory | Target Platform | Release Channel |
|---|---|---|
| **[`/extension`](./extension)** | VS Code Extension (`.vsix`) | VS Code Marketplace / GitHub Releases |
| **[`/desktop`](./desktop)** | Windows / macOS / Linux Desktop App | GitHub Releases (`.exe`, `.dmg`, `.AppImage`) |
| **[`/mobile`](./mobile)** | Android & iOS Supervisor App | Google Play Store / Apple App Store |

---

## 🛠️ Quick Start

```bash
# Install dependencies across all workspaces
npm install

# Compile the VS Code extension
npm run build:extension

# Run extension tests
npm run test
```