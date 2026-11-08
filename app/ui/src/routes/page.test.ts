import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
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
  Object.assign(maker, { ready: false, installed: null, check: null, songs: [], job: null, mixJob: null, error: '', draft: '' });
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

  it('makes a song from a link and opens it when done; keys and mixes come later, in the player', async () => {
    withTools();
    ipc.make_song = () => opened;
    render(Page);
    await fireEvent.input(await screen.findByRole('textbox', { name: 'YouTube link or audio file' }), {
      target: { value: 'https://youtu.be/x' },
    });
    expect(screen.queryByRole('button', { name: 'Down a semitone' })).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: 'Make song' }));
    expect(await screen.findByRole('heading', { name: 'Kad izdzisīs' })).toBeTruthy();
    expect(calls.find((c) => c.cmd === 'make_song')?.args).toEqual({
      source: 'https://youtu.be/x',
      library: '/m/Playalong',
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

describe('managing mixes', () => {
  const installed = { version: '2026.11.08', series: 1, commit: 'abc', model: 'sw' };
  const lower = { ...opened.song.mixes[0], file: 'mixes/s - guide -2.mp3', name: 'guide', transpose: -2 };
  const withNew = { ...opened, song: { ...opened.song, mixes: [...opened.song.mixes, lower] } };

  async function openPage() {
    ipc.runtime_status = () => ({ installed, busy: false });
    ipc.default_library = () => '/m/Playalong';
    ipc.list_library = () => [];
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open folder…' }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    return within(await screen.findByRole('region', { name: 'Mixes' }));
  }

  it('shows what the version has, makes what is ticked and missing, and remembers the ticks', async () => {
    localStorage.setItem('playalong.mixPicks', JSON.stringify({ presets: ['guide', 'drums-only'] }));
    ipc.make_mixes = () => withNew;
    const page = await openPage();
    expect(page.queryByRole('checkbox', { name: 'Guide' })).toBeNull();
    expect((page.getByRole('checkbox', { name: 'Drums only' }) as HTMLInputElement).checked).toBe(true);
    expect(page.getByRole('button', { name: 'Make 1' })).toBeTruthy();

    await fireEvent.click(page.getByRole('button', { name: 'Down a semitone' }));
    await fireEvent.click(page.getByRole('button', { name: 'Down a semitone' }));
    expect(page.getByText('−2 · G♯ minor')).toBeTruthy();
    expect((page.getByRole('checkbox', { name: 'Guide' }) as HTMLInputElement).checked).toBe(true);
    await fireEvent.click(page.getByRole('radio', { name: 'Off' }));
    await fireEvent.click(page.getByRole('button', { name: 'Make 2' }));

    expect(calls.find((c) => c.cmd === 'make_mixes')?.args).toEqual({
      folder: '/lib/kad-izdzisis',
      choice: { presets: ['guide', 'drums-only'], custom: null, transpose: -2, tempo: 1, count_in: 0, garageband: false },
    });
    expect(await page.findByRole('button', { name: /G♯m · 100% · 1 mix/ })).toBeTruthy();
    expect(page.queryByRole('checkbox', { name: 'Guide' })).toBeNull();
    expect(JSON.parse(localStorage.getItem('playalong.mixPicks')!).count_in).toBe(0);
  });

  it('makes only the GarageBand project', async () => {
    ipc.make_mixes = () => withNew;
    const page = await openPage();
    expect((page.getByRole('button', { name: 'Make' }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(page.getByRole('checkbox', { name: 'GarageBand project' }));
    await fireEvent.click(page.getByRole('button', { name: 'Make 1' }));
    const choice = (calls.find((c) => c.cmd === 'make_mixes')?.args as { choice: unknown }).choice;
    expect(choice).toMatchObject({ presets: [], custom: null, garageband: true });
  });

  it('makes your own mix from instrument levels', async () => {
    ipc.make_mixes = () => withNew;
    const page = await openPage();
    await fireEvent.click(page.getByRole('checkbox', { name: 'My mix' }));
    await fireEvent.click(page.getByRole('button', { name: 'Levels…' }));
    await fireEvent.input(page.getByRole('slider', { name: 'Guitar' }), { target: { value: '-12' } });
    await fireEvent.input(page.getByRole('slider', { name: 'Piano' }), { target: { value: '-25' } });
    expect(page.getByText(/guitar −12 dB, piano off/)).toBeTruthy();
    await fireEvent.click(page.getByRole('button', { name: 'Make 1' }));
    const choice = (calls.find((c) => c.cmd === 'make_mixes')?.args as { choice: { custom: unknown } }).choice;
    expect(choice.custom).toEqual({ vocals: 0, guitar: -12, bass: 0, drums: 0, piano: null, other: 0 });
  });

  it('plays a made mix from its row and goes back to the chords', async () => {
    const page = await openPage();
    const backing = within(page.getByText('Backing').closest('.row') as HTMLElement);
    await fireEvent.click(backing.getByRole('button', { name: 'Play' }));
    expect(backing.getByText(/playing/)).toBeTruthy();
    await fireEvent.click(page.getByRole('button', { name: '‹ Chords' }));
    expect(screen.queryByRole('region', { name: 'Mixes' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Edit', pressed: false })).toBeTruthy();
  });

  it('opens a GarageBand project the version has', async () => {
    const project = 'mixes/s - GarageBand 120 BPM.band';
    openResult = {
      ...opened,
      song: { ...opened.song, garagebands: [{ folder: 'mixes/s - GarageBand 120 BPM', bpm: 120, transpose: 0, project }] },
    };
    const page = await openPage();
    expect(page.queryByRole('checkbox', { name: 'GarageBand project' })).toBeNull();
    await fireEvent.click(page.getByRole('button', { name: 'Open' }));
    expect(calls.find((c) => c.cmd === 'open_in_garageband')?.args).toEqual({ folder: '/lib/kad-izdzisis', project });
  });

  it('says why mixes could not be made', async () => {
    ipc.make_mixes = () => {
      throw 'Busy: making a song';
    };
    const page = await openPage();
    await fireEvent.click(page.getByRole('checkbox', { name: 'GarageBand project' }));
    await fireEvent.click(page.getByRole('button', { name: 'Make 1' }));
    expect(await screen.findByText('Busy: making a song')).toBeTruthy();
  });
});
