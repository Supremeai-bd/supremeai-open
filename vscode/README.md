# SupremeAI Unified Client Hub (`supremeai-vscode`)

Native client applications and developer workflows for SupremeAI.  
Per [`ARCHITECTURE_PLAN.md`](https://github.com/Supremeai-bd/supremeai-open/blob/main/ARCHITECTURE_PLAN.md), this repository hosts all non-cloud client applications:

| Subdirectory | Target Platform | Release Channel |
|---|---|---|
| **[`/extension`](https://github.com/Supremeai-bd/supremeai-vscode/tree/main/extension)** | VS Code Extension (`.vsix`) | VS Code Marketplace / GitHub Releases |
| **[`/desktop`](https://github.com/Supremeai-bd/supremeai-vscode/tree/main/desktop)** | Windows / macOS / Linux Desktop App | GitHub Releases (`.exe`, `.dmg`, `.AppImage`) |
| **[`/mobile`](https://github.com/Supremeai-bd/supremeai-vscode/tree/main/mobile)** | Android & iOS Supervisor App | Google Play Store / Apple App Store |

> Satellite sovereignty (#4934): the `extension/`, `desktop/`, and `mobile/`
> sources live in the sovereign [`supremeai-vscode`](https://github.com/Supremeai-bd/supremeai-vscode)
> satellite repository; this hub keeps release docs and the root sentinel
> anchor (`package.json`) for zero-drift parity verification.

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