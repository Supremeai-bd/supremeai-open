// For more info, see https://github.com/storybookjs/eslint-plugin-storybook#configuration-flat-config-format
let storybookConfig = [];
try {
  const storybookModule = await import("eslint-plugin-storybook");
  const storybook = storybookModule.default || storybookModule;
  if (storybook?.configs?.["flat/recommended"]) {
    storybookConfig = [
      storybook.configs["flat/recommended"],
      {
        files: ['**/*.stories.{ts,tsx}'],
        rules: {
          'storybook/no-renderer-packages': 'off',
        },
      },
    ];
  }
} catch {
  // storybook plugin optional when not installed in slice
}

import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'


export default tseslint.config({ ignores: ['dist', 'dist-admin', 'dist-user', 'src/dataconnect-generated', 'coverage', 'node_modules'] }, {
  extends: [
    js.configs.recommended,
    ...tseslint.configs.recommended,
  ],
  files: ['**/*.{ts,tsx}'],
  languageOptions: {
    ecmaVersion: 2020,
    globals: globals.browser,
  },
  plugins: {
    'react-hooks': reactHooks,
    'react-refresh': reactRefresh,
  },
  rules: {
    ...reactHooks.configs.recommended.rules,
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true, allowExportNames: ['useTheme', 'useToast', 'useI18n', 'useThemeSync', 'useSwarmStream', 'setSujonState', 'useSujonState', 'SUJON_STATE_EVENT', 'SujonState', 'Theme', 'THEME_ORDER', 'ToastType', 'Toast', 'globalShowToastRef', 'useSujonMetrics', 'SujonHealthIndicator', 'SujonDashboardGrid', 'useSwarmArchitect', 'useAuthStatus', 'useSystemHealth', 'workspaceFeatureRoutes', 'SwarmArchitect'] },
    ],
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['warn', { 'argsIgnorePattern': '^_', 'varsIgnorePattern': '^_' }],
    'react-hooks/set-state-in-effect': 'off',
    'no-console': ['warn', { allow: ['warn', 'error', 'debug'] }],
    // Issue #2522: bare fetch() regression guard — সব API কল apiClient দিয়ে যাবে
    // (timeout, concurrency queue, auth header, cold-start retry, error mapping)।
    // Justified raw users নিচের override block-এ allowlisted।
    'no-restricted-syntax': ['warn', {
      selector: "CallExpression[callee.name='fetch']",
      message: "bare fetch() is forbidden (Issue #2522) — use apiClient from src/services/apiClient.ts (timeout/queue/auth/retry). For justified raw usage see the allowlist in eslint.config.js.",
    }],
  },
}, {
  // Issue #2522: justified bare-fetch allowlist — এই ফাইলগুলোতে raw fetch সচেতনভাবে রাখা হয়েছে:
  //  - apiClient.ts: ক্লায়েন্ট নিজেই প্রিমিটিভ লেয়ার
  //  - utils/api.ts: fetchWithRetry foundation (apiClient এই মডিউল import করে — circular এড়াতে)
  //  - firebase.ts: Firebase Hosting-এর নিজস্ব init endpoint (backend API নয়)
  //  - mcpViewer.ts: ইউজার-কনফিগার করা external MCP সার্ভার URL
  //  - storageApi.ts: Cloudflare R2 pre-signed PUT (external storage, backend বাইপাস)
  //  - GlobalErrorBoundary/RouteBoundary: keepalive unload-beacon (queue-তে গেলে unload-এ হারায়)
  files: [
    '**/services/apiClient.ts',
    '**/utils/api.ts',
    '**/services/TelemetryTracker.ts',
    '**/services/CrossAiObserverService.ts',
    '**/packages/shared-services/**',
    '**/firebase.ts',
    '**/services/mcpViewer.ts',
    '**/services/storageApi.ts',
    '**/components/GlobalErrorBoundary.tsx',
    '**/router/RouteBoundary.tsx',
    '**/main.tsx',
  ],
  rules: {
    'no-restricted-syntax': 'off',
  },
}, {
  // Test files: Allow any in tests (mocks, stubs, test fixtures)
  files: ['**/*.{test,spec}.{ts,tsx}', '**/test/**/*.{ts,tsx}'],
  rules: {
    '@typescript-eslint/no-explicit-any': 'off',
    'no-restricted-syntax': 'off',
  },
}, {
  // Routes and config files export route objects, not React components
  files: ['**/routes/**/*.{ts,tsx}', '**/routes.{ts,tsx}'],
  rules: {
    'react-refresh/only-export-components': 'off',
  },
}, ...storybookConfig);
