import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { clearMocks, mockIPC, mockWindows } from '@tauri-apps/api/mocks';
import ThemeToggle from './ThemeToggle.svelte';
import { THEME_KEY, storedTheme } from './theme';

let calls: { cmd: string; args: unknown }[];

beforeEach(() => {
  calls = [];
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  mockWindows('main');
  mockIPC((cmd, args) => {
    calls.push({ cmd, args });
    return null;
  });
});

afterEach(() => {
  cleanup();
  clearMocks();
});

const windowTheme = () =>
  calls.filter((c) => c.cmd === 'plugin:window|set_theme').map((c) => (c.args as { value: unknown }).value);

describe('theme toggle', () => {
  it('follows the system until toggled', () => {
    render(ThemeToggle);
    expect(storedTheme()).toBe('system');
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(screen.getByRole('button', { name: 'Dark appearance' })).toBeTruthy();
  });

  it('switches to dark, remembers it, and darkens the window too', async () => {
    render(ThemeToggle);
    await fireEvent.click(screen.getByRole('button', { name: 'Dark appearance' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem(THEME_KEY)).toBe('dark');
    await waitFor(() => expect(windowTheme()).toContain('dark'));
    expect(screen.getByRole('button', { name: 'Light appearance' })).toBeTruthy();
  });

  it('switches back to light from a remembered dark', async () => {
    localStorage.setItem(THEME_KEY, 'dark');
    render(ThemeToggle);
    await fireEvent.click(screen.getByRole('button', { name: 'Light appearance' }));
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem(THEME_KEY)).toBe('light');
    await waitFor(() => expect(windowTheme()).toContain('light'));
  });
});
