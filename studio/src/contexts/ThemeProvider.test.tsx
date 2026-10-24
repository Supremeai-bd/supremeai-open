import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { ThemeProvider } from './ThemeProvider';
import { useTheme } from './useTheme';
import { THEME_ORDER } from './ThemeConstants';

// Test consumer component
const TestThemeConsumer: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="current-theme">{theme}</span>
      <button data-testid="toggle-btn" onClick={toggleTheme}>
        Toggle
      </button>
    </div>
  );
};

describe('ThemeProvider (Issue #494)', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = '';
    document.documentElement.removeAttribute('data-theme');
    document.body.className = '';
    document.body.removeAttribute('data-theme');
    vi.clearAllMocks();
  });

  it('initializes with default dark theme and applies DOM classes', () => {
    render(
      <ThemeProvider>
        <TestThemeConsumer />
      </ThemeProvider>
    );

    expect(screen.getByTestId('current-theme')).toHaveTextContent('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.body.classList.contains('dark')).toBe(true);
    expect(document.body.getAttribute('data-theme')).toBe('dark');
  });

  it('cycles across all themes in order according to THEME_ORDER', async () => {
    render(
      <ThemeProvider>
        <TestThemeConsumer />
      </ThemeProvider>
    );

    const toggleBtn = screen.getByTestId('toggle-btn');
    const themeSpan = screen.getByTestId('current-theme');

    for (let i = 1; i < THEME_ORDER.length; i++) {
      const nextTheme = THEME_ORDER[i];
      await act(async () => {
        fireEvent.click(toggleBtn);
      });
      expect(themeSpan).toHaveTextContent(nextTheme);
      expect(document.documentElement.classList.contains(nextTheme)).toBe(true);
      expect(document.documentElement.getAttribute('data-theme')).toBe(nextTheme);
    }

    // Wrap back to the first theme ('dark')
    await act(async () => {
      fireEvent.click(toggleBtn);
    });
    expect(themeSpan).toHaveTextContent('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('persists selected theme in localStorage', async () => {
    render(
      <ThemeProvider>
        <TestThemeConsumer />
      </ThemeProvider>
    );

    const toggleBtn = screen.getByTestId('toggle-btn');
    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    const stored = localStorage.getItem('supremeai-theme-storage');
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored!).state.theme).toBe('light');
  });
});
