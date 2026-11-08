// The app's own update, from GitHub Releases: downloaded quietly at start, applied on the next restart.

import { check } from '@tauri-apps/plugin-updater';

export const appUpdate = $state({ ready: '' });

export async function checkAppUpdate() {
  try {
    const update = await check();
    if (!update) return;
    await update.downloadAndInstall();
    appUpdate.ready = update.version;
  } catch {
    // Offline, or the release isn't there yet: the app works as it is, and the next start tries again.
  }
}
