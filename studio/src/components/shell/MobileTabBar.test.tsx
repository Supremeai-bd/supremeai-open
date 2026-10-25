import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { MobileTabBar } from './MobileTabBar';
import { DashboardLayout } from '../layout/DashboardLayout';
import { useMobileNav } from '../../hooks/useMobileNav';

// বাংলা: P1 wave item 4 (2026-10-25 report) — মোবাইল বটম ট্যাব বার। এন্ট্রি
// navigationRegistry (SIMPLE_VIEWER_ENTRY_IDS) থেকে derive হয় — টেস্টটি যাচাই করে
// (১) registry-derived ৩+More ট্যাব, (২) active state, (৩) More → ড্রয়ার স্টোর,
// (৪) DashboardLayout স্লট রেন্ডার + main bottom padding, (৫) admin-safe surface।

function renderTabBar(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <MobileTabBar />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useMobileNav.setState({ isMobileNavOpen: false });
});

describe('MobileTabBar (P1 wave item 4)', () => {
  it('renders the registry-derived user level-1 tabs plus More', () => {
    // Owner decision 2026-10-24: user rail = nav-chat, nav-profile, nav-settings.
    renderTabBar('/workspace');
    expect(screen.getByTestId('mobile-tab-bar')).toBeInTheDocument();
    expect(screen.getByTestId('mobile-tab-nav-chat')).toHaveTextContent('Chat');
    expect(screen.getByTestId('mobile-tab-nav-profile')).toHaveTextContent('Profile');
    expect(screen.getByTestId('mobile-tab-nav-settings')).toHaveTextContent('Settings');
    expect(screen.getByTestId('mobile-tab-more')).toHaveTextContent('More');
    // Tabs navigate via routes — links carry real hrefs (dead-link prevention).
    expect(screen.getByTestId('mobile-tab-nav-chat')).toHaveAttribute('href', '/workspace/live');
  });

  it('marks the tab whose route prefix matches the current path active', () => {
    renderTabBar('/workspace/live');
    expect(screen.getByTestId('mobile-tab-nav-chat')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByTestId('mobile-tab-nav-profile')).not.toHaveAttribute('aria-current');
  });

  it('opens the existing mobile nav drawer (level-2 surface) from More', async () => {
    const user = userEvent.setup();
    renderTabBar('/workspace');
    expect(useMobileNav.getState().isMobileNavOpen).toBe(false);
    await user.click(screen.getByTestId('mobile-tab-more'));
    expect(useMobileNav.getState().isMobileNavOpen).toBe(true);
  });

  it('DashboardLayout renders the mobileTabBar slot and pads main content on mobile', () => {
    render(
      <MemoryRouter initialEntries={['/workspace']}>
        <DashboardLayout mobileTabBar={<MobileTabBar />}>
          <div>page-body</div>
        </DashboardLayout>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('mobile-tab-bar')).toBeInTheDocument();
    expect(screen.getByText('page-body')).toBeInTheDocument();
    const main = screen.getByText('page-body').parentElement as HTMLElement;
    expect(main.className).toContain('pb-[calc(4rem+env(safe-area-inset-bottom))]');
    expect(main.className).toContain('md:pb-0');
  });

  it('without the slot, main has no bottom padding (admin surface unchanged)', () => {
    render(
      <MemoryRouter initialEntries={['/workspace']}>
        <DashboardLayout>
          <div>admin-body</div>
        </DashboardLayout>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('mobile-tab-bar')).not.toBeInTheDocument();
    const main = screen.getByText('admin-body').parentElement as HTMLElement;
    expect(main.className).not.toContain('pb-');
  });
});
