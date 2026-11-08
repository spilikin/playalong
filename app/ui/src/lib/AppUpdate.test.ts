import { fireEvent, render, screen } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const updater = vi.hoisted(() => ({ check: vi.fn(), relaunch: vi.fn() }));
vi.mock('@tauri-apps/plugin-updater', () => ({ check: updater.check }));
vi.mock('@tauri-apps/plugin-process', () => ({ relaunch: updater.relaunch }));

import AppUpdate from './AppUpdate.svelte';
import { appUpdate, checkAppUpdate } from './selfUpdate.svelte';
import { maker } from './maker.svelte';

describe('app update', () => {
  beforeEach(() => {
    updater.check.mockReset();
    updater.relaunch.mockReset();
    appUpdate.ready = '';
    maker.job = null;
  });

  it('downloads a new version in the background, then offers a restart', async () => {
    const downloadAndInstall = vi.fn().mockResolvedValue(undefined);
    updater.check.mockResolvedValue({ version: '0.2.0', downloadAndInstall });
    render(AppUpdate);
    expect(screen.queryByRole('button')).toBeNull();

    await checkAppUpdate();
    expect(downloadAndInstall).toHaveBeenCalled();
    await fireEvent.click(await screen.findByRole('button', { name: /restart/i }));
    expect(updater.relaunch).toHaveBeenCalled();
  });

  it('stays out of the way when there is nothing new or no network', async () => {
    updater.check.mockResolvedValueOnce(null);
    await checkAppUpdate();
    updater.check.mockRejectedValueOnce(new Error('offline'));
    await checkAppUpdate();
    render(AppUpdate);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('waits with the restart while a song is being made', async () => {
    appUpdate.ready = '0.2.0';
    maker.job = { source: 'x', transpose: 0, lines: [], running: true, error: '', made: null };
    render(AppUpdate);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
