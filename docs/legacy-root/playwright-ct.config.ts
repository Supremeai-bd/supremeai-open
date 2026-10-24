import { defineConfig, devices } from '@playwright/experimental-ct-react';
import react from '@vitejs/plugin-react';

/**
 * Playwright Component Testing কনফিগারেশন।
 * এটি Vite ব্যবহার করে React কম্পোনেন্টগুলোকে মাউন্ট করে এবং টেস্ট করে।
 */
export default defineConfig({
    testDir: './frontend/src', // কম্পোনেন্ট এবং টেস্ট ফাইলগুলো যেখানে আছে
    testMatch: '**/*.ct.spec.tsx',   // কম্পোনেন্ট টেস্ট ফাইলের নামের প্যাটার্ন
    snapshotDir: './tests/ct-snapshots', // কম্পোনেন্ট টেস্টের স্ন্যাপশট রাখার জন্য
    timeout: 10 * 1000,
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : undefined,
    reporter: [['html', { outputFolder: 'playwright-ct-report' }]],

    use: {
        // Vite-এর জন্য React প্লাগইন কনফিগার করা হচ্ছে
        ctViteConfig: {
            plugins: [react()],
        },
        trace: 'on-first-retry',
    },

    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
        {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] },
        },
    ],
});
