// বাংলা মন্তব্য (Wave 3): BillingPage contract-fix টেস্ট — পেজটি দীর্ঘদিন ভুল
// প্রিফিক্সের নির্জীব plans path কল করছিল। এই টেস্টগুলো প্রকৃত ব্যাকএন্ড
// কনট্র্যাক্ট lock করে: GET /api/billing/plans (dict-shaped plans!), GET
// /api/billing/wallet, POST /api/billing/checkout — এবং honest error state।
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

// বাংলা: WorkspaceLayout (UnifiedAppShell) ভারী — পেজ লজিক টেস্টে হালকা stub।
vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { BillingPage } from './BillingPage';
import { apiClient } from '../services/apiClient';

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

// বাংলা: ব্যাকএন্ড GET /api/billing/plans সত্যিই dict রিটার্ন করে
// (SUBSCRIPTION_PLANS: dict[str, SubscriptionPlan]) — list নয়।
const PLANS_RESPONSE = {
  plans: {
    free: {
      id: 'price_free',
      name: 'Free Plan',
      price: 0,
      cost: 0,
      currency: 'usd',
      interval: 'month',
      features: ['100 AI Credits', 'Basic Models'],
    },
    pro: {
      id: 'price_pro_monthly',
      name: 'Pro Plan',
      price: 9.99,
      cost: 9.99,
      currency: 'usd',
      interval: 'month',
      features: ['1000 AI Credits', 'Advanced Models'],
    },
  },
};

const renderPage = () => render(<BillingPage />);

describe('BillingPage (Wave 3 contract fix)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGet.mockImplementation((path: string) => {
      if (path === '/api/billing/plans') return Promise.resolve(PLANS_RESPONSE);
      if (path === '/api/billing/wallet') {
        return Promise.resolve({ user_id: 'u1', balance_usd: 5, monthly_allowance_usd: 0 });
      }
      return Promise.resolve({});
    });
  });

  it('fetches plans from the real /api/billing/plans contract and renders the dict', async () => {
    renderPage();
    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/api/billing/plans');
    });
    expect(await screen.findByText('Pro Plan')).toBeInTheDocument();
    expect(screen.getByText('Free Plan')).toBeInTheDocument();
    // price + interval backend-সত্য ফিল্ড থেকে এসেছে
    expect(screen.getByText('$9.99')).toBeInTheDocument();
    expect(screen.getAllByText('/month').length).toBeGreaterThan(0);
  });

  it('shows an honest error state when the plans endpoint fails', async () => {
    mockedGet.mockImplementation((path: string) => {
      if (path === '/api/billing/plans') return Promise.reject(new Error('billing offline'));
      if (path === '/api/billing/wallet') {
        return Promise.resolve({ user_id: 'u1', balance_usd: 5, monthly_allowance_usd: 0 });
      }
      return Promise.resolve({});
    });
    renderPage();
    expect(await screen.findByTestId('billing-plans-error')).toBeInTheDocument();
    expect(screen.getByText('billing offline')).toBeInTheDocument();
  });

  it('renders the real wallet balance from /api/billing/wallet', async () => {
    renderPage();
    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith('/api/billing/wallet');
    });
    expect(await screen.findByTestId('billing-wallet-balance')).toBeInTheDocument();
    expect(screen.getByText('$5.00')).toBeInTheDocument();
  });

  it('starts checkout via POST /api/billing/checkout and surfaces the no-URL honesty path', async () => {
    // বাংলা: URL ছাড়া response = কোনো ভুয়া success নয় — honest error দৃশ্যমান হবে।
    mockedPost.mockResolvedValue({ status: 'success' });
    renderPage();
    const button = await screen.findByTestId('billing-checkout-btn-price_pro_monthly');
    await userEvent.click(button);

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/billing/checkout', {
        price_id: 'price_pro_monthly',
        success_url: window.location.href,
        cancel_url: window.location.href,
      });
    });
    expect(await screen.findByTestId('billing-checkout-error')).toHaveTextContent(
      'Checkout did not return a payment URL.',
    );
  });
});
