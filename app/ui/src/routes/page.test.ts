import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { clearMocks, mockIPC, mockWindows } from '@tauri-apps/api/mocks';
import { opened } from '$lib/fixture';
import Page from './+page.svelte';

let calls: { cmd: string; args: unknown }[];
let openResult: unknown;

beforeEach(() => {
  calls = [];
  openResult = opened;
  localStorage.clear();
  mockWindows('main');
  mockIPC((cmd, args) => {
    calls.push({ cmd, args });
    if (cmd === 'plugin:dialog|open') return '/lib/kad-izdzisis';
    if (cmd === 'open_song') {
      if (typeof openResult === 'string') throw openResult;
      return openResult;
    }
    return null;
  });
  // The IPC mock leaves out the asset-URL helper the real app provides.
  (window as unknown as { __TAURI_INTERNALS__: Record<string, unknown> }).__TAURI_INTERNALS__.convertFileSrc = (
    path: string,
  ) => `asset://localhost/${encodeURIComponent(path)}`;
});

// Listener setup and teardown are asynchronous; let them finish before the mocks go.
const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

afterEach(async () => {
  await settle();
  cleanup();
  await settle();
  clearMocks();
});

describe('player', () => {
  it('opens a song folder and shows its mixes with the guide mix chosen', async () => {
    render(Page);
    await fireEvent.click(screen.getByRole('button', { name: 'Open song folder…' }));
    expect(await screen.findByRole('heading', { name: 'Kad izdzisīs' })).toBeTruthy();
    expect(calls.find((c) => c.cmd === 'open_song')?.args).toEqual({ path: '/lib/kad-izdzisis' });
    expect(screen.getByRole('button', { name: 'Guide' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'No guitar' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('Bb minor')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /^Bar / })).toHaveLength(2);
  });

  it('lists the four main mixes in order, the rest under More, and switches with keys 1–4', async () => {
    render(Page);
    await fireEvent.click(screen.getByRole('button', { name: 'Open song folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    const tray = screen.getByRole('navigation', { name: 'Mixes' });
    const names = [...tray.querySelectorAll('button')].map((b) => b.getAttribute('aria-label'));
    expect(names).toEqual(['Original', 'Guide', 'No guitar', 'Vocals only', 'Backing']);
    await fireEvent.keyDown(window, { code: 'Digit4', key: '4' });
    expect(screen.getByRole('button', { name: 'Vocals only' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('shows the album cover', async () => {
    render(Page);
    await fireEvent.click(screen.getByRole('button', { name: 'Open song folder…' }));
    const img = (await screen.findByRole('img', { name: 'Tā Mana Dzīve' })) as HTMLImageElement;
    expect(decodeURIComponent(img.src)).toContain('/lib/kad-izdzisis/cover.jpg');
  });

  it('says why a folder could not be opened', async () => {
    openResult = 'No song file in /lib/x. Run `playalong chords` on this folder to create one.';
    render(Page);
    await fireEvent.click(screen.getByRole('button', { name: 'Open song folder…' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('playalong chords'));
  });

  it('remembers opened songs for next time', async () => {
    const first = render(Page);
    await fireEvent.click(screen.getByRole('button', { name: 'Open song folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    first.unmount();
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'kad-izdzisis' }));
    await waitFor(() => expect(calls.filter((c) => c.cmd === 'open_song')).toHaveLength(2));
  });
});

describe('Roks ir dzīvs!', () => {
  it('a triple click on the wordmark switches to Latvian and back, and is remembered', async () => {
    const first = render(Page);
    const mark = screen.getByLabelText('Roks ir dzīvs!');
    await fireEvent.click(mark, { detail: 1 });
    expect(screen.getByRole('button', { name: 'Open song folder…' })).toBeTruthy();
    await fireEvent.click(mark, { detail: 3 });
    expect(screen.getByRole('button', { name: 'Atvērt dziesmas mapi…' })).toBeTruthy();
    first.unmount();
    render(Page);
    expect(screen.getByRole('button', { name: 'Atvērt dziesmas mapi…' })).toBeTruthy();
    await fireEvent.click(screen.getByLabelText('Roks ir dzīvs!'), { detail: 3 });
    expect(screen.getByRole('button', { name: 'Open song folder…' })).toBeTruthy();
  });
});

describe('restart', () => {
  it('stops the song, goes back to the start of the mix and the top of the sheet', async () => {
    const scrollTo = vi.fn();
    const { container } = render(Page);
    await fireEvent.click(screen.getByRole('button', { name: 'Open song folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    (container.querySelector('.sheet-wrap') as HTMLElement).scrollTo = scrollTo;
    const audio = container.querySelector('audio') as HTMLAudioElement;
    const pause = vi.fn();
    audio.pause = pause;
    audio.currentTime = 42;
    await fireEvent.click(screen.getByRole('button', { name: 'Restart' }));
    expect(audio.currentTime).toBe(0);
    expect(pause).toHaveBeenCalled();
    await waitFor(() => expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'auto' }));
    expect(scrollTo).toHaveBeenCalledTimes(1);
  });
});
