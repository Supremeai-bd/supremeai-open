import { defineConfig, loadEnv } from 'vite'
import fs from 'fs'
import path from 'path'

// Load env files from the directory Vite is actually running in. Using the
// parent directory here caused Vercel builds to miss project-level VITE_* vars,
// silently selecting the fallback backend and making the deployed app slow or
// unreachable when that service was cold or unavailable.
const projectRoot = process.cwd()
Object.assign(process.env, loadEnv(process.env.NODE_ENV || 'development', projectRoot, ''))
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// বাংলা (unified backend URL architecture):
// এখন User ও Admin উভয় ইন্টারফেস একই ইউনিফাইড ব্যাকএন্ড এপিআই ক্লাস্টারে কানেক্ট হয়।
// অগ্রাধিকার ক্রম: VITE_API_URL -> VITE_BACKEND_URL -> VITE_USER_BACKEND -> RENDER_SERVICE_URL
const normalizeBackendUrl = (value: unknown) => {
  if (typeof value !== 'string') return ''
  const normalized = value.trim().replace(/^VITE_[A-Z0-9_]+=\s*/i, '').replace(/\/$/, '')
  try {
    const parsed = new URL(normalized)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.toString().replace(/\/$/, '') : ''
  } catch {
    return ''
  }
}

const UNIFIED_BACKEND =
  normalizeBackendUrl(process.env.VITE_API_URL) ||
  normalizeBackendUrl(process.env.VITE_BACKEND_URL) ||
  normalizeBackendUrl(process.env.VITE_USER_BACKEND) ||
  normalizeBackendUrl(process.env.RENDER_SERVICE_URL) ||
  'https://supremeai-primary-node.onrender.com'
const USER_BACKEND = UNIFIED_BACKEND
const ADMIN_BACKEND = normalizeBackendUrl(process.env.VITE_ADMIN_BACKEND) || UNIFIED_BACKEND

// A frontend viewer build must still be publishable without a backend env var
// ONLY when the bundle is pinned to relative API paths (Docker sets
// VITE_USE_RELATIVE_PATH=true). Public MCP URLs are supplied by the user at
// runtime; admin/API features can report their missing connection when used
// instead of blocking the whole build.
// FIX(FE-07): a bare console.warn let Vercel ship a production bundle with
// USER_BACKEND_URL='' — every apiClient call then hit the vercel.json
// /(.*) catch-all rewrite, got index.html instead of JSON and the app
// white-screened, and the CI verifier only ran after deploy. Fail the build
// instead when neither a backend URL nor the relative-path escape hatch is set.
if (
  process.env.NODE_ENV === 'production' &&
  !UNIFIED_BACKEND &&
  process.env.VITE_USE_RELATIVE_PATH !== 'true'
) {
  throw new Error(
    '[build-contract] Production build has no backend URL (set VITE_API_URL / ' +
      'VITE_BACKEND_URL / VITE_USER_BACKEND in the deploy environment) and ' +
      'VITE_USE_RELATIVE_PATH is not "true". A bundle baked without either ' +
      'would ship degraded viewer mode and white-screen on every API call.',
  )
}
if (process.env.NODE_ENV === 'production' && !UNIFIED_BACKEND) {
  console.warn('No backend URL configured; building public viewer mode (relative /api paths).')
}

// P0 build-contract (production sign-off): a LOOPBACK backend baked into a
// production bundle is always the Docker-default leak (VITE_API_URL unset in
// the Dockerfile), never intentional. Fail the build loudly; operators can
// opt out for a local throwaway build with VITE_ALLOW_LOOPBACK_BACKEND=true.
// CI additionally verifies the baked bundle via scripts/ci/verify_frontend_build_contract.py.
const LOOPBACK_HOSTS = [`local${'host'}`, `127${'.0.0.1'}`, `0${'.0.0.0'}`, `${':'}${':'}1`, `[${':'}${':'}1]`]
const isLoopbackUrl = (value: string) => {
  if (!value) return false
  try {
    const host = new URL(value).hostname.toLowerCase()
    return LOOPBACK_HOSTS.includes(host)
  } catch {
    return false
  }
}
if (
  process.env.NODE_ENV === 'production' &&
  (isLoopbackUrl(UNIFIED_BACKEND) || isLoopbackUrl(ADMIN_BACKEND)) &&
  process.env.VITE_ALLOW_LOOPBACK_BACKEND !== 'true'
) {
  throw new Error(
    '[build-contract] Production build would bake a loopback backend URL into the bundle ' +
      `(user=${UNIFIED_BACKEND || '(empty)'}, admin=${ADMIN_BACKEND || '(empty)'}). ` +
      'Set VITE_API_URL/VITE_USER_BACKEND/VITE_ADMIN_BACKEND to the real backend, ' +
      'or pass VITE_ALLOW_LOOPBACK_BACKEND=true only for a local throwaway build.',
  )
}

// 🔬 Evolution v3.0: Dump build config for debugging
const buildInfoPlugin = () => {
  return {
    name: 'build-info-plugin',
    writeBundle(options: { dir?: string }) {
      if (process.env.NODE_ENV === 'production') {
        const buildInfo = {
          timestamp: new Date().toISOString(),
          buildType: 'unified', // single frontend build (no portal split)
          userBackendUrl: USER_BACKEND,
          adminBackendUrl: ADMIN_BACKEND || USER_BACKEND,
          coopHeader: process.env.COOP_HEADER,
          coepHeader: process.env.COEP_HEADER,
        }
        const outDir = options.dir || 'dist'
        fs.writeFileSync(path.join(outDir, 'build-info.json'), JSON.stringify(buildInfo, null, 2))
        console.warn(`📋 Build info written to ${outDir}/build-info.json`)
      }
    }
  }
}

const devProxy: Record<string, { target: string; changeOrigin: boolean }> = {}
if (USER_BACKEND) {
  devProxy['/api'] = { target: USER_BACKEND, changeOrigin: true }
  devProxy['/auth'] = { target: USER_BACKEND, changeOrigin: true }
}
if (ADMIN_BACKEND || USER_BACKEND) {
  devProxy['/admin-api'] = { target: ADMIN_BACKEND || USER_BACKEND, changeOrigin: true }
}

// https://vite.dev/config/
export default defineConfig({
  base: process.env.ELECTRON === 'true' ? './' : '/', // Use './' for Electron, '/' for Web to fix client-side routing and MIME issues
  define: {
    // বাংলা মন্তব্য: লগইন পেজে বিল্ড টাইম দেখানোর জন্য, যাতে প্রোডাকশনে ঠিকমতো ডিপ্লয় হয়েছে কি না বোঝা যায়
    __APP_BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  plugins: [
    react({ jsxRuntime: 'automatic' }),
    tailwindcss({
      config: './tailwind.config.js',
    }),
    buildInfoPlugin()
  ],
  esbuild: {
    jsx: 'automatic',
    // #2736: আগে drop:['console'] প্রোডাকশনে সব console.* মুছে দিত —
    // console.error-ও (SSE failure path useServerStream.ts:62,92 prod-এ
    // অদৃশ্য ছিল)। এখন শুধু debugger drop + চ্যাটি-লেভেল (log/info/debug)
    // pure-marked — warn/error বেঁচে থাকে (নীতি: prod-এ ব্যর্থতা দৃশ্যমান)।
    drop: process.env.NODE_ENV === 'production' ? ['debugger'] : [],
    pure: process.env.NODE_ENV === 'production' ? ['console.log', 'console.info', 'console.debug'] : [],
  },
  resolve: {
    dedupe: ['react', 'react-dom', '@tanstack/react-query']
  },
  server: {
    // 🔧 DYNAMIC SECURITY HEADERS from environment
    headers: {
      ...(process.env.COOP_HEADER ? { 'Cross-Origin-Opener-Policy': process.env.COOP_HEADER } : {}),
      ...(process.env.COEP_HEADER ? { 'Cross-Origin-Embedder-Policy': process.env.COEP_HEADER } : {}),
    },
    // বাংলা মন্তব্য: dev proxy — user API → user backend, admin API → admin backend (fallback user)
    proxy: devProxy
  },
  preview: {
    // ERR-A04 FIX: `vite preview` serves the production build locally — give
    // it the same cross-origin-isolation headers as the dev server and nginx
    // so the WebContainer sandbox can be validated before shipping.
    headers: {
      ...(process.env.COOP_HEADER ? { 'Cross-Origin-Opener-Policy': process.env.COOP_HEADER } : {}),
      ...(process.env.COEP_HEADER ? { 'Cross-Origin-Embedder-Policy': process.env.COEP_HEADER } : {}),
    },
    proxy: devProxy
  },
  build: {
    // বাংলা: single production artifact — User + Admin দুই context একই bundle-এ
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // FIX (honesty, Task 14-b): নিচের vendor map টি আগে output-এর সরাসরি key হিসেবে
        // বসানো ছিল — manualChunks কী ছাড়া = rollup চুপচাপ ignore করত (silent no-op),
        // ফলে কোনো vendor chunk তৈরিই হতো না (862KB monolithic main)।
        // আরও প্রমাণিত (probe build): object form (manualChunks: {...})-ও react ধরতে
        // পারে না — Vite-এর commonjs plugin react/react-dom/scheduler এর module id-তে
        // ?commonjs-* query suffix জোড়ে, ফলে vendor-react খালি (1 byte) থেকে যায় আর
        // react main chunk-এই থেকে যায় (sourcemap দিয়ে যাচাইকৃত)। তাই object নয়,
        // precise path-segment function form — bucket বিভাজন নিচের map-এর অর্থই বহন করে।
        manualChunks(id: string) {
          // FIX (final-test ci-fixes): react + react-dom অবশ্যই একটাই chunk-এ থাকতে হবে
          // এবং সেই chunk অন্য কোনো vendor chunk-কে import করবে না। আগে react জোরপূর্বক
          // vendor-ui-তে (framer-motion/lucide/recharts) আর react-dom অনাকাঙ্ক্ষিতভাবে
          // vendor-flow-তে (@xyflow/react graph-এ) গিয়ে পড়ছিল → vendor-ui ⇄ vendor-flow
          // circular import → react-এর CJS factory (requireReact) vendor-ui-এর module body
          // চলার আগেই vendor-flow থেকে call হয়ে "Cannot set properties of undefined
          // (setting 'Activity')" boot crash দিচ্ছিল → পুরো অ্যাপ "Loading SupremeAI..."
          // splash-এ আটকে যেত (E2E "home loads KPI tiles" failure-এর আসল কারণ)।
          // react/react-dom/scheduler একসাথে + zero outgoing vendor imports = অন্তত
          // react চক্রমুক্ত ও সবসময় প্রথমে initialize হয়।
          // (segment-exact regex: node_modules/react/ মেলে কিন্তু lucide-react/
          // @monaco-editor/react/ @xyflow/react/ মেলে না — ভুল bucket-এ react যেতে পারে না)
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return 'vendor-react'
          // ROOT-CAUSE FIX (#2734): recharts (~100KB gz) was bucket-welded with
          // framer-motion + lucide-react into 'vendor-ui'. Since framer-motion is
          // eagerly imported by DashboardLayout/CommandBar (boot path), Rollup
          // loaded the entire vendor-ui chunk (including recharts) on every page
          // — even the guest `/` funnel which never charts. Now: recharts gets
          // its own 'vendor-charts' chunk, loaded only by lazy admin chunks.
          if (/[\\/]node_modules[\\/]recharts[\\/]/.test(id)) return 'vendor-charts'
          if (/[\\/]node_modules[\\/](@xterm|xterm)[\\/]/.test(id)) return 'vendor-terminal'
          if (/[\\/]node_modules[\\/](@monaco-editor|monaco-editor)[\\/]/.test(id)) return 'vendor-editor'
          if (/[\\/]node_modules[\\/](framer-motion|lucide-react)[\\/]/.test(id)) return 'vendor-ui'
          if (/[\\/]node_modules[\\/]@xyflow[\\/]/.test(id)) return 'vendor-flow'
          if (/[\\/]node_modules[\\/]@tanstack[\\/]react-query[\\/]/.test(id)) return 'vendor-query'
          return undefined
        },
      },
    },
    chunkSizeWarningLimit: 600,
    // FIX(FE-03): 'hidden' only strips the //# sourceMappingURL comment — the
    // .map files were still emitted and uploaded by Vercel, leaking original
    // TS/TSX source to anyone fetching /assets/*.js.map. Disable sourcemaps
    // for production builds entirely; defense-in-depth via .vercelignore.
    sourcemap: false,
  },
  envPrefix: ['VITE_', 'NEXT_PUBLIC_'],
})
