// The app's own update, from GitHub Releases: downloaded quietly at start, installed only when the person
// restarts. Installing replaces the app on disk, including the Python code it runs songs with, so it has to
// wait until nothing is running.

import { check, type Update } from '@tauri-apps/plugin-updater';
import { relaunch } from '@tauri-apps/plugin-process';

export const appUpdate = $state({ ready: '' });

let pending: Update | null = null;

export async function checkAppUpdate() {
  try {
    const update = await check();
    if (!update) return;
    await update.download();
    pending = update;
    appUpdate.ready = update.version;
  } catch {
    // Offline, or the release isn't there yet: the app works as it is, and the next start tries again.
  }
}

export async function restartToUpdate() {
  await pending?.install();
  await relaunch();
}
