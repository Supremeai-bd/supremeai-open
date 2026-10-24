// apps/studio-client/src/pages/BillingPage.tsx
// Subscription & Token Billing Page
// বাংলা মন্তব্য: বিলিং ও সাবস্ক্রিপশন ব্যবস্থাপনা পেজ — সম্পূর্ণ ফ্রি-টিয়ার এবং অন-ডিমান্ড টোকেন প্ল্যান।
//
// Wave 3 contract fix: এই পেজ দীর্ঘদিন ভুল প্রিফিক্সের (`/api/v1/...`) plans
// endpoint কল করছিল — অথচ ব্যাকএন্ড বিলিং ফ্যামিলি সম্পূর্ণ /api/billing/*-এ
// (docs/generated/route_inventory.json)। ফলে plans প্রতি লোডে 404 খেত এবং পেজ
// সবসময় খালি state দেখাত। এখন প্রকৃত কনট্র্যাক্ট (backend/api/routes/billing_api.py +
// backend/services/billing/billing_plans.py):
//   GET  /api/billing/plans   → { plans: Record<string, SubscriptionPlan> } (dict keyed by name!)
//   GET  /api/billing/wallet  → { user_id, balance_usd, monthly_allowance_usd }
//   POST /api/billing/checkout (price_id, success_url, cancel_url) → { status, session_id, url }
// SubscriptionPlan ফিল্ড: { id, name, price, cost, currency, interval, features }।
// Frontend type শুধু ব্যবহৃত ফিল্ডগুলোই ধরে — আগের description/current/buttonText
// ছিল কল্পিত ফিল্ড (ব্যাকএন্ড কখনো পাঠায়নি), তাই বাদ দেওয়া হয়েছে। কোনো ডেটা বানানো হয়নি।

import React, { useEffect, useState } from 'react';
import { Zap, CheckCircle2, ShieldCheck, CreditCard } from 'lucide-react';
import { apiClient } from '../services/apiClient';
import { WorkspaceLayout } from '../components/layout/WorkspaceLayout';
import { useListResource } from '../hooks/useListResource';

interface BillingPlan {
  id: string;
  name: string;
  price: number;
  currency: string;
  interval: string;
  features: string[];
}

interface WalletBalance {
  user_id: string;
  balance_usd: number;
  monthly_allowance_usd: number;
}

const usd = (amount: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);

export const BillingPage: React.FC = () => {
  const {
    items: plans,
    isLoading,
    loadError,
    reload: loadPlans,
  } = useListResource<BillingPlan>({
    fetcher: async () => {
      const response = await apiClient.get<{ plans?: Record<string, BillingPlan> }>('/api/billing/plans');
      // বাংলা: ব্যাকএন্ডে plans একটি dict (plan name → SubscriptionPlan), list নয় —
      // Object.values দিয়ে সত্যিই array বানানো হচ্ছে; dict-এর insertion order
      // (free, pro, enterprise) JSON-এও preserved থাকে।
      return Object.values(response.plans ?? {});
    },
  });

  const [wallet, setWallet] = useState<WalletBalance | null>(null);
  const [walletLoading, setWalletLoading] = useState(true);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [checkoutBusyId, setCheckoutBusyId] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiClient.get<WalletBalance>('/api/billing/wallet')
      .then((res) => { if (active) setWallet(res); })
      .catch((err) => { if (active) setWalletError(err instanceof Error ? err.message : 'Wallet unavailable'); })
      .finally(() => { if (active) setWalletLoading(false); });
    return () => { active = false; };
  }, []);

  const startCheckout = async (plan: BillingPlan) => {
    setCheckoutBusyId(plan.id);
    setCheckoutError(null);
    try {
      const res = await apiClient.post<{ status?: string; url?: string }>(
        '/api/billing/checkout',
        {
          price_id: plan.id,
          success_url: window.location.href,
          cancel_url: window.location.href,
        },
      );
      if (res?.url) {
        window.location.assign(res.url);
        return;
      }
      // বাংলা: URL ছাড়া "সফল" checkout বলে কিছু নেই — ভুয়া success দেখানো নিষেধ।
      setCheckoutError('Checkout did not return a payment URL.');
    } catch (err) {
      setCheckoutError(err instanceof Error ? err.message : 'Checkout failed.');
    } finally {
      setCheckoutBusyId(null);
    }
  };

  return (
    // বাংলা (single-frontend migration): page-level NavRail shell সরিয়ে একক shared
    // shell-এ আনা হলো (roadmap Rule 8: no duplicate global shells)।
    <WorkspaceLayout>
      <main className="p-8 max-w-6xl mx-auto w-full">
        <header className="mb-10">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-cyan-500/20 text-cyan-400">
              <Zap className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">Billing & Subscriptions</h1>
              <p className="text-sm text-slate-400">Manage your subscription, usage quotas, and payment gateways</p>
            </div>
          </div>
        </header>

        {/* Wallet strip — real /api/billing/wallet data, honest loading/error/empty states */}
        <div
          className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-12"
          data-testid="billing-wallet"
        >
          <div className="flex items-center gap-4">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
              <CreditCard className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-200">Wallet balance</h3>
              <p className="text-xs text-slate-400">Spent against this balance as you run workloads.</p>
            </div>
          </div>
          {walletLoading ? (
            <span className="text-sm text-slate-400" data-testid="billing-wallet-loading">Loading wallet balance...</span>
          ) : walletError ? (
            <span role="alert" data-testid="billing-wallet-error" className="text-sm text-red-400">Wallet unavailable: {walletError}</span>
          ) : wallet ? (
            <span className="text-sm text-slate-300" data-testid="billing-wallet-balance">
              <span className="text-2xl font-extrabold text-slate-100">{usd(wallet.balance_usd)}</span>
              {wallet.monthly_allowance_usd > 0 && (
                <span className="ml-3 text-xs text-slate-400">
                  + {usd(wallet.monthly_allowance_usd)} monthly allowance
                </span>
              )}
            </span>
          ) : (
            <span className="text-sm text-slate-400" data-testid="billing-wallet-empty">Wallet not initialized yet.</span>
          )}
        </div>

        {/* Pricing Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
          {isLoading && <div className="md:col-span-2 rounded-2xl border border-slate-800 bg-slate-900/40 p-8 text-center text-sm text-slate-400">Loading available plans...</div>}
          {!isLoading && loadError && (
            <div
              role="alert"
              data-testid="billing-plans-error"
              className="md:col-span-2 flex flex-col gap-3 rounded-2xl border border-red-500/40 bg-red-500/5 p-6 text-sm sm:flex-row sm:items-center"
            >
              <span className="text-red-400">{loadError}</span>
              <button
                type="button"
                onClick={() => void loadPlans()}
                className="rounded-xl border border-slate-700 px-3 py-1.5 font-medium text-slate-300 transition hover:border-cyan-500 sm:ml-auto"
              >
                Try again
              </button>
            </div>
          )}
          {!isLoading && !loadError && plans.length === 0 && <div className="md:col-span-2 rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-8 text-center text-sm text-slate-400">No billing plans are currently available.</div>}
          {plans.map((plan) => (
            <div
              key={plan.id}
              className="rounded-2xl border border-slate-800 bg-slate-900/40 hover:border-slate-700 p-8 flex flex-col justify-between transition-all"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-slate-200">{plan.name}</h2>
                </div>
                <div className="flex items-baseline gap-1 mb-4">
                  <span className="text-4xl font-extrabold">{usd(plan.price)}</span>
                  <span className="text-sm text-slate-400">/{plan.interval}</span>
                </div>
                <ul className="space-y-3 mb-8">
                  {(plan.features ?? []).map((feature) => (
                    <li key={feature} className="flex items-center gap-3 text-sm text-slate-300">
                      <CheckCircle2 className="h-4 w-4 text-cyan-400" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <button
                type="button"
                data-testid={`billing-checkout-btn-${plan.id}`}
                onClick={() => void startCheckout(plan)}
                disabled={checkoutBusyId === plan.id}
                className="w-full py-3 px-4 rounded-xl font-semibold text-sm transition-all bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-lg shadow-cyan-500/25 disabled:opacity-50"
              >
                {checkoutBusyId === plan.id ? 'Starting checkout…' : 'Subscribe'}
              </button>
            </div>
          ))}
        </div>

        {checkoutError && (
          <p role="alert" data-testid="billing-checkout-error" className="mb-12 border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
            {checkoutError}
          </p>
        )}

        {/* Security & Gateways Info */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <ShieldCheck className="h-8 w-8 text-emerald-400" />
            <div>
              <h3 className="font-semibold text-slate-200">Plan protection</h3>
              <p className="text-xs text-slate-400">All basic workloads are routed automatically through free-tier providers.</p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-slate-400 text-xs">
            <CreditCard className="h-4 w-4" /> SSLCommerz & Stripe Verified
          </div>
        </div>
      </main>
    </WorkspaceLayout>
  );
};

export default BillingPage;
