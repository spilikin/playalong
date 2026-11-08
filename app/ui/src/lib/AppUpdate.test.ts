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
    maker.installing = false;
  });

  it('downloads a new version in the background and installs it only on restart', async () => {
    const download = vi.fn().mockResolvedValue(undefined);
    const install = vi.fn().mockResolvedValue(undefined);
    updater.check.mockResolvedValue({ version: '0.2.0', download, install });
    render(AppUpdate);
    expect(screen.queryByRole('button')).toBeNull();

    await checkAppUpdate();
    expect(download).toHaveBeenCalled();
    expect(install).not.toHaveBeenCalled();
    await fireEvent.click(await screen.findByRole('button', { name: /restart/i }));
    expect(install).toHaveBeenCalled();
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

  it('waits with the restart while the audio tools are installing', async () => {
    appUpdate.ready = '0.2.0';
    maker.installing = true;
    render(AppUpdate);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
