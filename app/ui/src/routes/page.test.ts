import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { clearMocks, mockIPC, mockWindows } from '@tauri-apps/api/mocks';
import { opened } from '$lib/fixture';
import { maker } from '$lib/maker.svelte';
import Page from './+page.svelte';

let calls: { cmd: string; args: unknown }[];
let openResult: unknown;
// Answers for the song-making commands, per test.
let ipc: Record<string, (args: unknown) => unknown>;

beforeEach(() => {
  calls = [];
  openResult = opened;
  ipc = {};
  Object.assign(maker, { ready: false, installed: null, check: null, songs: [], job: null, error: '', draft: '' });
  localStorage.clear();
  mockWindows('main');
  mockIPC((cmd, args) => {
    calls.push({ cmd, args });
    if (cmd in ipc) return ipc[cmd](args);
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
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    expect(await screen.findByRole('heading', { name: 'Kad izdzisīs' })).toBeTruthy();
    expect(calls.find((c) => c.cmd === 'open_song')?.args).toEqual({ path: '/lib/kad-izdzisis' });
    expect(screen.getByRole('button', { name: 'Guide' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'No guitar' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('Bb minor')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /^Bar / })).toHaveLength(2);
  });

  it('lists the four main mixes in order, the rest under More, and switches with keys 1–4', async () => {
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    const tray = screen.getByRole('navigation', { name: 'Mixes' });
    const names = [...tray.querySelectorAll('button')].map((b) => b.getAttribute('aria-label'));
    expect(names).toEqual(['Original', 'Guide', 'No guitar', 'Vocals only', 'Backing']);
    await fireEvent.keyDown(window, { code: 'Digit4', key: '4' });
    expect(screen.getByRole('button', { name: 'Vocals only' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('shows the album cover', async () => {
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    const img = (await screen.findByRole('img', { name: 'Tā Mana Dzīve' })) as HTMLImageElement;
    expect(decodeURIComponent(img.src)).toContain('/lib/kad-izdzisis/cover.jpg');
  });

  it('says why a folder could not be opened', async () => {
    openResult = 'No song file in /lib/x. Run `playalong chords` on this folder to create one.';
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('playalong chords'));
  });

  it('remembers opened songs for next time', async () => {
    const first = render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
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
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    const mark = await screen.findByLabelText('Roks ir dzīvs!');
    await fireEvent.click(mark, { detail: 1 });
    expect(screen.getByRole('button', { name: 'Open…' })).toBeTruthy();
    await fireEvent.click(mark, { detail: 3 });
    expect(screen.getByRole('button', { name: 'Atvērt…' })).toBeTruthy();
    first.unmount();
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Atvērt dziesmas mapi…' }));
    await fireEvent.click(await screen.findByLabelText('Roks ir dzīvs!'), { detail: 3 });
    expect(screen.getByRole('button', { name: 'Open…' })).toBeTruthy();
  });
});

describe('restart', () => {
  it('stops the song, goes back to the start of the mix and the top of the sheet', async () => {
    const scrollTo = vi.fn();
    const { container } = render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
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

describe('library', () => {
  const installed = { version: '2026.11.07', series: 1, commit: 'abc', model: 'sw' };
  const song = { folder: '/m/Playalong/kad', title: 'Kad izdzisīs', artist: 'Miks Galvanovskis', key: 'Bb minor',
    bpm: 79.9, mixes: 8, transposed: [-2], cover: null, added: 1_780_000_000 };

  function withTools() {
    ipc.runtime_status = () => ({ installed, busy: false });
    ipc.default_library = () => '/m/Playalong';
    ipc.list_library = () => [song];
    ipc.runtime_check = () => ({ plan: { runtime: null, model: null, version: '2026.11.07' }, download_size: 0 });
  }

  it('without the audio tools, offers to download them with their size', async () => {
    ipc.runtime_status = () => ({ installed: null, busy: false });
    ipc.runtime_check = () => ({
      plan: { runtime: { file: 'rt', size: 150e6 }, model: { file: 'm', size: 340e6 }, version: '2026.11.07' },
      download_size: 490e6,
    });
    ipc.runtime_install = () => installed;
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Download audio tools · 490 MB' }));
    expect(calls.some((c) => c.cmd === 'runtime_install')).toBe(true);
    expect(await screen.findByRole('heading', { name: 'Library' })).toBeTruthy();
  });

  it('lists the songs, finds them by name and opens one', async () => {
    withTools();
    render(Page);
    const row = await screen.findByRole('button', { name: /Kad izdzisīs/ });
    expect(row.textContent).toContain('B♭m');
    expect(row.textContent).toContain('−2');
    await fireEvent.input(screen.getByRole('searchbox', { name: 'Search songs' }), { target: { value: 'bee gees' } });
    expect(screen.getByText('No songs match.')).toBeTruthy();
    await fireEvent.input(screen.getByRole('searchbox', { name: 'Search songs' }), { target: { value: 'miks' } });
    await fireEvent.click(screen.getByRole('button', { name: /Kad izdzisīs/ }));
    expect(await screen.findByRole('heading', { name: 'Kad izdzisīs' })).toBeTruthy();
    expect(calls.find((c) => c.cmd === 'open_song')?.args).toEqual({ path: '/m/Playalong/kad' });
  });

  it('makes a song from a link in another key and opens it when done', async () => {
    withTools();
    ipc.make_song = () => opened;
    render(Page);
    await fireEvent.input(await screen.findByRole('textbox', { name: 'YouTube link or audio file' }), {
      target: { value: 'https://youtu.be/x' },
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Down a semitone' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Down a semitone' }));
    expect(screen.getByText('Key: −2')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Make song' }));
    expect(await screen.findByRole('heading', { name: 'Kad izdzisīs' })).toBeTruthy();
    expect(calls.find((c) => c.cmd === 'make_song')?.args).toEqual({
      source: 'https://youtu.be/x',
      library: '/m/Playalong',
      transpose: -2,
    });
  });

  it('goes back from the player to the Library', async () => {
    withTools();
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: /Kad izdzisīs/ }));
    await fireEvent.click(await screen.findByRole('button', { name: '‹ Library' }));
    expect(await screen.findByRole('heading', { name: 'Library' })).toBeTruthy();
  });

  it('says why a song could not be made', async () => {
    withTools();
    ipc.make_song = () => {
      throw 'ERROR: Video unavailable';
    };
    render(Page);
    await fireEvent.input(await screen.findByRole('textbox', { name: 'YouTube link or audio file' }), {
      target: { value: 'https://youtu.be/gone' },
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Make song' }));
    expect(await screen.findByText('ERROR: Video unavailable')).toBeTruthy();
  });
});
