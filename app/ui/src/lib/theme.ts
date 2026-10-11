import { getCurrentWindow } from '@tauri-apps/api/window';

export type ThemeChoice = 'system' | 'light' | 'dark';

export const THEME_KEY = 'playalong.theme';

export function storedTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

/** Light or dark regardless of the system, or back to following it; the window's title bar follows too. */
export async function applyTheme(choice: ThemeChoice): Promise<void> {
  const root = document.documentElement;
  if (choice === 'system') delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Without storage the choice just lasts until the app closes.
  }
  try {
    await getCurrentWindow().setTheme(choice === 'system' ? null : choice);
  } catch {
    // Outside the app (or without the permission) only the page changes, which is what matters.
  }
}
