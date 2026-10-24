import { fileURLToPath, URL } from 'url';

export default {
  test: {
    environment: 'node',
    globals: true,
    include: ['test/**/*.test.ts'],
    setupFiles: ['./test/setup.ts'],
    ssr: false,
    deps: {
      interopDefault: true,
    },
  },
  resolve: {
    alias: [
      { find: /^vscode$/, replacement: fileURLToPath(new URL('./test/mocks/vscode.ts', import.meta.url)) },
    ],
  },
  coverage: {
    provider: 'v8',
  },
} as any;
