import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { JarvisAdminGate } from './JarvisAdminGate';
import * as totpUtils from '../../../utils/totp';

describe('JarvisAdminGate', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('bypasses gate immediately when 7-day trusted token is valid in localStorage', () => {
    const onUnlocked = vi.fn();
    const future = Date.now() + 1000 * 60 * 60 * 24 * 7;
    localStorage.setItem('jarvis_admin_trusted_until', future.toString());

    render(<JarvisAdminGate onUnlocked={onUnlocked} />);
    expect(onUnlocked).toHaveBeenCalledTimes(1);
  });

  it('unlocks with emergency master PIN 1955 and stores 7-day trust when checked', async () => {
    const onUnlocked = vi.fn();
    render(<JarvisAdminGate onUnlocked={onUnlocked} />);

    const input = screen.getByPlaceholderText('000 000');
    fireEvent.change(input, { target: { value: '1955' } });

    const authBtn = screen.getByRole('button', { name: /AUTHENTICATE/i });
    fireEvent.click(authBtn);

    await waitFor(() => {
      expect(onUnlocked).toHaveBeenCalledTimes(1);
    });

    const trusted = Number(localStorage.getItem('jarvis_admin_trusted_until'));
    expect(trusted).toBeGreaterThan(Date.now() + 1000 * 60 * 60 * 24 * 6);
  });

  it('verifies 6-digit TOTP code and auto-submits upon 6 digits', async () => {
    const onUnlocked = vi.fn();
    vi.spyOn(totpUtils, 'verifyTotpCode').mockResolvedValue(true);

    render(<JarvisAdminGate onUnlocked={onUnlocked} />);

    const input = screen.getByPlaceholderText('000 000');
    fireEvent.change(input, { target: { value: '123456' } });

    await waitFor(() => {
      expect(totpUtils.verifyTotpCode).toHaveBeenCalledWith('123456', expect.any(String), 1);
      expect(onUnlocked).toHaveBeenCalledTimes(1);
    });
  });

  it('shows error message on incorrect code', async () => {
    const onUnlocked = vi.fn();
    vi.spyOn(totpUtils, 'verifyTotpCode').mockResolvedValue(false);

    render(<JarvisAdminGate onUnlocked={onUnlocked} />);

    const input = screen.getByPlaceholderText('000 000');
    fireEvent.change(input, { target: { value: '999999' } });

    await waitFor(() => {
      expect(screen.getByText(/Invalid Authenticator code|Access denied/i)).toBeInTheDocument();
      expect(onUnlocked).not.toHaveBeenCalled();
    });
  });

  it('opens and closes Google Authenticator setup modal with QR code option', async () => {
    const onUnlocked = vi.fn();
    render(<JarvisAdminGate onUnlocked={onUnlocked} />);

    const setupBtn = screen.getByRole('button', { name: /Setup Authenticator/i });
    fireEvent.click(setupBtn);

    expect(screen.getByText(/Setup Google Authenticator/i)).toBeInTheDocument();
    expect(screen.getByText(/Scan this QR code with/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByAltText(/Google Authenticator QR Code/i)).toBeInTheDocument();
    });

    const closeBtn = screen.getByRole('button', { name: /Close setup modal/i });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText(/Scan this QR code with/i)).not.toBeInTheDocument();
    });
  });
});
