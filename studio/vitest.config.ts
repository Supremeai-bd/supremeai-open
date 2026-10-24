import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    // বাংলা মন্তব্য: মনোরিপোর অন্যান্য প্রোজেক্টের React 18-এর সাথে সংঘর্ষ এড়াতে এবং টেস্টে React 19 নিশ্চিত করতে লোকাল পাথ সেট করা হলো
    alias: {
      'react': path.resolve(__dirname, './node_modules/react'),
      'react-dom': path.resolve(__dirname, './node_modules/react-dom'),
    },
    dedupe: ['react', 'react-dom'],
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      // বাংলা মন্তব্য: আগে শুধু components/customer ও hooks মাপা হতো। এখন store/services/
      // providers/core যোগ করা হলো (integration-সংবেদনশীল লেয়ার)। pages ইউআই স্ন্যাপশট
      // চার্নের জন্য বাদ রাখা হয়েছে।
      include: [
        'src/components/**/*.{ts,tsx}',
        'src/commandcenter/**/*.{ts,tsx}',
        'src/hooks/**/*.{ts,tsx}',
        'src/store/**/*.{ts,tsx}',
        'src/services/**/*.{ts,tsx}',
        'src/providers/**/*.{ts,tsx}',
        'src/core/**/*.{ts,tsx}',
        'src/i18n/**/*.{ts,tsx}',
      ],
      exclude: ['**/*.d.ts', '**/test/**', '**/*.test.*', '**/*.spec.*', 'src/pages/**'],
      thresholds: {
        lines: 10,
        functions: 10,
        branches: 10,
        statements: 10
      }
    },
  },
});
