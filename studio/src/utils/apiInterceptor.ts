// frontend/src/utils/apiInterceptor.ts
// 🛡️ Global fetch interceptor — cookie-scoping + structured error normalization.
//
// DRY Phase 1-B4 cleanup: the unused `apiInterceptor<T>()` response-wrapper
// export was removed (zero importers — only `setupGlobalFetchInterceptor`
// below is consumed, by src/main.tsx). Response envelope/error-shaping now
// has ONE home: the canonical transport (packages/shared-services
// createHttpClient) plus this live global hook.

export function setupGlobalFetchInterceptor() {
  if (typeof window === 'undefined') return;

  const originalFetch = window.fetch;

  window.fetch = async function (...args) {
    const url = args[0];
    let options: RequestInit | undefined = args[1] as RequestInit;
    const apiBase = (await import('./api')).getApiBaseUrl();

    // FIX (P2, review 2026-09-12): with VITE_USE_RELATIVE_PATH=true the apiBase is
    // '' and `''.startsWith(...)` matches EVERY url — cookies were attached to
    // cross-origin calls (Supabase, R2 uploads, telemetry), breaking CORS.
    // Guard against an empty base and only target same-origin/app API URLs.
    if (
      apiBase &&
      (typeof url === 'string'
        ? url.startsWith(apiBase)
        : url instanceof URL && url.origin === window.location.origin)
    ) {
      options = options || {};
      options.credentials = 'include';
      args[1] = options;
    }

    try {
      const response = await originalFetch.apply(this, args);

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          // বাংলা মন্তব্য (PREVENT SPURIOUS LOGOUT / NO BARABARI):
          // ক্ষণস্থায়ী নেটওয়ার্ক ফল্ট, কোল্ড স্টার্ট বা ব্যাকগ্রাউন্ড এন্ডপয়েন্ট ফেইলরে
          // কখনো অ্যাডমিনকে মাঝপথে অহেতুক লগআউট করানো যাবে না। অ্যাডমিন শুধুমাত্র তখন লগআউট হবে
          // যখন সে নিজে Logout বাটনে চাপ দেবে অথবা নিশ্চিত সেশন রিভোক ঘটবে।
          if (import.meta.env.DEV) {
            console.warn(`[Interceptor] Endpoint returned ${response.status} (Unauthorized/Forbidden):`, url);
          }
        }

        let errorMsg = `HTTP Error ${response.status}: ${response.statusText}`;
        try {
          const clone = response.clone();
          const text = await clone.text();
          if (text) {
            const parsed = JSON.parse(text);
            // বাংলা মন্তব্য: React #31 crash রোধ — backend/Google-স্টাইল `{code,message,errors}` envelope
            // যদি object হয় তাহলে সেটাকে সর্বদা string-এ রূপান্তর করবো, যেন toast/render-এ
            // "Objects are not valid as a React child (found: object with keys {code,message,errors})" না ঘটে।
            const toMsgString = (v: unknown): string | null =>
              typeof v === 'string'
                ? v
                : v && typeof v === 'object'
                  ? JSON.stringify(v)
                  : v === undefined || v === null
                    ? null
                    : String(v);
            errorMsg =
              toMsgString(parsed.error) ??
              toMsgString(parsed.message) ??
              toMsgString(parsed.detail) ??
              text.slice(0, 50);
          }
        } catch (e) {
          console.error('🚨 [INTERCEPTOR_ERROR]: Failed to parse error response', e);
        }

        const rawUrl = typeof url === 'string'
          ? url
          : url instanceof Request
            ? url.url
            : url instanceof URL
              ? url.href
              : String(url || '');

        const isPublicHealthProbe = rawUrl.includes('/api/health-aggregation');
        const isBackgroundRequest = (
          isPublicHealthProbe ||
          rawUrl.includes('/api/config') ||
          rawUrl.includes('/api/health') ||
          rawUrl.includes('/connections') ||
          rawUrl.includes('/conversations') ||
          rawUrl.includes('/workspace') ||
          rawUrl.includes('/preferences') ||
          rawUrl.includes('/models') ||
          rawUrl.includes('/skills')
        );
        const isGuestOrChat = rawUrl.includes('/chat/completions') || rawUrl.includes('/v1/');

        // বাংলা মন্তব্য (UX পলিসি): 404 (Not Found), 401/403 (Auth/Session), বা ব্যাকগ্রাউন্ড
        // কুয়েরির ক্ষেত্রে কোনো গ্লোবাল লাল টোস্ট পপআপ দেখানো যাবে না। কলার কম্পোনেন্টগুলো (UserDashboard,
        // WorkspaceSettings ইত্যাদি) নিজেরাই নিজস্ব গ্রেসফুল ফলব্যাক বা এম্পটি স্টেট দেখায়।
        const isExpectedSilentStatus = response.status === 404 || response.status === 401 || response.status === 403;
        const isNotFoundError = errorMsg.toLowerCase().includes('not found') || response.status === 404;

        const win = window as unknown as { showGlobalToast?: (type: string, msg: string) => void };
        if (win.showGlobalToast && !isBackgroundRequest && !isGuestOrChat && !isExpectedSilentStatus && !isNotFoundError) {
          win.showGlobalToast('error', errorMsg);
        }
      }

      return response;
    } catch (error) {
      // বাংলা মন্তব্য: নেটওয়ার্ক বা কানেকশন ফেইলিয়রে ইউজারের স্ক্রিনে "Unable to connect" গ্লোবাল টোস্ট দেখানো
      // ইউজার এক্সপেরিয়েন্স নষ্ট করে। কলার ফাংশনগুলো (GlobalConfigInitializer, GuestChat ইত্যাদি) নিজেরাই
      // নিজস্ব গ্রেসফুল ফলব্যাক বা রিট্রাই হ্যান্ডেল করে। তাই এখানে গ্লোবাল পপআপ বন্ধ করে নীরবে লগ রাখা হলো।
      console.warn('⚠️ [API_INTERCEPTOR_FETCH_ERROR]:', error instanceof Error ? error.message : error);
      throw error;
    }
  };
}
