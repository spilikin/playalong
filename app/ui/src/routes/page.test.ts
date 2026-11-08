import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { clearMocks, mockIPC, mockWindows } from '@tauri-apps/api/mocks';
import { emit } from '@tauri-apps/api/event';
import { opened } from '$lib/fixture';
import { maker } from '$lib/maker.svelte';
import { DEFAULT_MIXES, type Recipe } from '$lib/mixes';
import { playback } from '$lib/playback.svelte';
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
  Object.assign(playback, { folder: '', mixes: [], current: '', timeline: null, mixSeconds: 0, duration: 0, playing: false, saveError: '' });
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
    if (cmd === 'playback_open') return { duration: 30, timeline: TIMELINE, mixes: DEFAULT_MIXES, current: 'original' };
    if (cmd === 'playback_set_mix') {
      const recipe = (args as { recipe: { tempo: number } }).recipe;
      return { ...TIMELINE, tempo: recipe.tempo };
    }
    return null;
  }, { shouldMockEvents: true });
  // The IPC mock leaves out the asset-URL helper the real app provides.
  (window as unknown as { __TAURI_INTERNALS__: Record<string, unknown> }).__TAURI_INTERNALS__.convertFileSrc = (
    path: string,
  ) => `asset://localhost/${encodeURIComponent(path)}`;
});

// The fixture song's timing as the engine gives it for a mix at full tempo with a one-bar count-in.
const TIMELINE = {
  tempo: 1,
  source_offset: 20,
  count_in: {
    bars: 1,
    clicks: [0.25, 0.75, 1.25, 1.75].map((time, i) => ({ time, accent: i === 0, count: i + 1 })),
    downbeat: 2.25,
  },
};

const heard = (mixSeconds: number, playing = true) => emit('playback-position', { mix_seconds: mixSeconds, playing });

// Listener setup and teardown are asynchronous; let them finish before the mocks go.
const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

afterEach(async () => {
  await settle();
  cleanup();
  await settle();
  clearMocks();
});

describe('player', () => {
  async function openSong() {
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    return screen.findByRole('heading', { name: 'Kad izdzisīs' });
  }

  it('opens a song folder and plays its mixes live, the first one chosen', async () => {
    await openSong();
    expect(calls.find((c) => c.cmd === 'open_song')?.args).toEqual({ path: '/lib/kad-izdzisis' });
    expect(calls.find((c) => c.cmd === 'playback_open')?.args).toEqual({ folder: '/lib/kad-izdzisis', mix: null });
    expect(screen.getByRole('button', { name: /^Original/ }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('Bb minor')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /^Bar / })).toHaveLength(2);
  });

  it('plays through the engine and follows its position', async () => {
    await openSong();
    await fireEvent.click(screen.getByRole('button', { name: 'Play' }));
    expect(calls.some((c) => c.cmd === 'playback_play')).toBe(true);
    await heard(4.5);
    await waitFor(() => expect(screen.getByRole('figure', { name: 'Now' }).textContent).toContain('A♭'));
    await heard(1.3);
    await waitFor(() => expect(document.querySelector('.count .number')?.textContent).toBe('3'));
  });

  it('switches mix without reopening, keeping the place, and with keys 1–3', async () => {
    await openSong();
    await fireEvent.click(screen.getByRole('button', { name: /^No guitar/ }));
    expect(calls.find((c) => c.cmd === 'playback_set_mix')?.args).toEqual({ recipe: DEFAULT_MIXES[2] });
    expect(calls.filter((c) => c.cmd === 'playback_open')).toHaveLength(1);
    expect(screen.getByRole('button', { name: /^No guitar/ }).getAttribute('aria-pressed')).toBe('true');
    await fireEvent.keyDown(window, { code: 'Digit2', key: '2' });
    expect(screen.getByRole('button', { name: /^Guide/ }).getAttribute('aria-pressed')).toBe('true');
  });

  it('shows the chords moved when the mix is in another key', async () => {
    openResult = {
      ...opened,
      song: { ...opened.song, transpositions: { '-2': { key: 'G# minor', chords: { Bbm: 'G#m', Ab: 'F#' } } } },
    };
    ipc.playback_open = () => ({
      duration: 30,
      timeline: TIMELINE,
      mixes: [{ ...DEFAULT_MIXES[0], name: 'Lower', transpose: -2 }],
      current: 'original',
    });
    await openSong();
    expect(screen.getByText('G# minor')).toBeTruthy();
  });

  it('brings a song from before live mixes up to date first', async () => {
    openResult = { ...opened, song: { ...opened.song, version: 1 } };
    maker.installed = { version: '2026.11.08', series: 1, commit: 'abc', model: 'sw' };
    ipc.runtime_status = () => ({ installed: maker.installed, busy: false });
    ipc.default_library = () => '/m/Playalong';
    ipc.list_library = () => [];
    ipc.song_refresh = () => opened;
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    const order = calls.map((c) => c.cmd).filter((c) => c === 'song_refresh' || c === 'playback_open');
    expect(order).toEqual(['song_refresh', 'playback_open']);
  });

  it('brings an old song given at launch up to date once it knows the audio tools are there', async () => {
    openResult = { ...opened, song: { ...opened.song, version: 1 } };
    let answer: (v: unknown) => void = () => {};
    ipc.runtime_status = () => new Promise((resolve) => (answer = resolve));
    ipc.default_library = () => '/m/Playalong';
    ipc.list_library = () => [];
    ipc.launch_args = () => ({ path: '/m/Playalong/kad', at: null });
    ipc.song_refresh = () => opened;
    render(Page);
    await settle();
    answer({ installed: { version: '2026.11.08', series: 1, commit: 'abc', model: 'sw' }, busy: false });
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    expect(calls.some((c) => c.cmd === 'song_refresh')).toBe(true);
  });

  it('says an old song needs the audio tools to be brought up to date', async () => {
    openResult = { ...opened, song: { ...opened.song, version: 1 } };
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('audio tools'));
    expect(calls.some((c) => c.cmd === 'playback_open')).toBe(false);
  });

  it('shows the album cover', async () => {
    await openSong();
    const img = screen.getByRole('img', { name: 'Tā Mana Dzīve' }) as HTMLImageElement;
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
    await heard(42);
    await fireEvent.click(screen.getByRole('button', { name: 'Restart' }));
    expect(calls.some((c) => c.cmd === 'playback_pause')).toBe(true);
    await waitFor(() => expect(calls.find((c) => c.cmd === 'playback_seek')?.args).toEqual({ mixSeconds: 0 }));
    await waitFor(() => expect(scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'auto' }));
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

describe('editing mixes', () => {
  async function openSong() {
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
  }

  async function edit() {
    await openSong();
    await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    return within(await screen.findByRole('region', { name: 'Mixer' }));
  }

  const lastMix = () =>
    (calls.filter((c) => c.cmd === 'playback_set_mix').at(-1)?.args as { recipe: Recipe } | undefined)?.recipe;

  it('Edit shows the mixer of the mix playing in place of the chords, Done goes back', async () => {
    const mixer = await edit();
    expect(screen.getByRole('button', { name: 'Done', pressed: true })).toBeTruthy();
    expect(mixer.getByRole('heading', { name: 'Original' })).toBeTruthy();
    expect(screen.queryByRole('region', { name: 'Chords' })).toBeNull();
    await fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.getByRole('region', { name: 'Chords' })).toBeTruthy();
  });

  it('renames a mix and keeps it, without rendering anything', async () => {
    await edit();
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name of Guide' }), { target: { value: 'Band' } });
    await waitFor(() =>
      expect((calls.find((c) => c.cmd === 'mixes_save')?.args as { mixes: Recipe[] }).mixes[1].name).toBe('Band'),
    );
    expect(calls.some((c) => c.cmd.startsWith('song_'))).toBe(false);
  });

  it('a level, mute, solo, key or tempo change is heard at once', async () => {
    const mixer = await edit();
    await fireEvent.input(mixer.getByRole('slider', { name: 'Guitar' }), { target: { value: '-12' } });
    expect(lastMix()?.levels.guitar).toBe(-12);
    await fireEvent.click(mixer.getByRole('button', { name: 'Mute Vocals' }));
    expect(lastMix()?.mute).toEqual(['vocals']);
    await fireEvent.click(mixer.getByRole('button', { name: 'Solo Drums' }));
    expect(lastMix()?.solo).toEqual(['drums']);
    await fireEvent.click(mixer.getByRole('button', { name: 'Down a semitone' }));
    await fireEvent.click(mixer.getByRole('button', { name: 'Slower' }));
    expect(lastMix()).toMatchObject({ transpose: -1, tempo: 0.95 });
    await fireEvent.click(mixer.getByRole('radio', { name: '2 bars' }));
    expect(lastMix()?.count_in).toBe(2);
    await fireEvent.click(mixer.getByRole('button', { name: 'No guitar' }));
    expect(lastMix()).toMatchObject({ mute: ['guitar'], solo: [], transpose: -1 });
  });

  it('makes, duplicates, moves and deletes mixes', async () => {
    await edit();
    await fireEvent.click(screen.getByRole('button', { name: '+ New mix' }));
    expect(screen.getByRole('textbox', { name: 'Name of Original copy' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Original copy' })).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'More for Guide' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: 'Move up' }));
    await fireEvent.click(screen.getByRole('button', { name: 'More for No guitar' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }));
    const names = screen.getAllByRole('textbox', { name: /^Name of / }).map((i) => (i as HTMLInputElement).value);
    expect(names).toEqual(['Guide', 'Original', 'Original copy']);
    await waitFor(() =>
      expect((calls.filter((c) => c.cmd === 'mixes_save').at(-1)?.args as { mixes: Recipe[] }).mixes).toHaveLength(3),
    );
  });

  it('exports a mix as an MP3', async () => {
    ipc.song_export = () => '/lib/kad-izdzisis/exports/kad - Guide.mp3';
    await edit();
    await fireEvent.click(screen.getByRole('button', { name: 'More for Guide' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: 'Export MP3…' }));
    expect(calls.find((c) => c.cmd === 'song_export')?.args).toEqual({ folder: '/lib/kad-izdzisis', mix: 'guide' });
    expect(await screen.findByText(/shown in Finder/)).toBeTruthy();
  });

  it('without the song’s tempo the count-in is off and says why', async () => {
    openResult = { ...opened, song: { ...opened.song, tempo: null } };
    const mixer = await edit();
    expect((mixer.getByRole('radio', { name: '1 bar' }) as HTMLInputElement).disabled).toBe(true);
    expect(mixer.getByText(/needs the song’s tempo/)).toBeTruthy();
  });
});

describe('song editing', () => {
  async function songPanel() {
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open song folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    await fireEvent.click(screen.getByRole('button', { name: 'Song…' }));
    return within(await screen.findByRole('region', { name: 'Song' }));
  }

  it('sets where the song starts to the playhead, then plays on with the new timing', async () => {
    ipc.song_retime = () => opened;
    const panel = await songPanel();
    await heard(4.5);
    await fireEvent.click(panel.getByRole('button', { name: 'Set to playhead' }));
    expect(calls.find((c) => c.cmd === 'song_retime')?.args).toEqual({ folder: '/lib/kad-izdzisis', start: 24.5, bpm: null });
    await waitFor(() => expect(calls.filter((c) => c.cmd === 'playback_open')).toHaveLength(2));
    await waitFor(() => expect(calls.find((c) => c.cmd === 'playback_seek')?.args).toEqual({ mixSeconds: 4.5 }));
  });

  it('taps the tempo and sets it', async () => {
    ipc.song_retime = () => opened;
    const now = vi.spyOn(performance, 'now');
    const panel = await songPanel();
    for (const t of [1000, 1500, 2000, 2500, 3000]) {
      now.mockReturnValue(t);
      await fireEvent.click(panel.getByRole('button', { name: 'Tap' }));
    }
    expect((panel.getByRole('spinbutton', { name: 'BPM' }) as HTMLInputElement).value).toBe('120');
    await fireEvent.click(panel.getByRole('button', { name: 'Set BPM' }));
    expect(calls.find((c) => c.cmd === 'song_retime')?.args).toEqual({ folder: '/lib/kad-izdzisis', start: null, bpm: 120 });
    now.mockRestore();
  });

  it('finds the chords again', async () => {
    ipc.song_retime = () => opened;
    const panel = await songPanel();
    await fireEvent.click(panel.getByRole('button', { name: 'Detect again' }));
    expect(calls.find((c) => c.cmd === 'song_retime')?.args).toEqual({ folder: '/lib/kad-izdzisis', start: null, bpm: null });
  });

  it('builds a GarageBand project in a key; one left behind by a timing change offers Make again', async () => {
    const project = 'mixes/s - GarageBand 120 BPM -1.band';
    openResult = {
      ...opened,
      song: { ...opened.song, garagebands: [{ folder: 'mixes/s - GarageBand 120 BPM -1', bpm: 120, transpose: -1, project, outdated: true }] },
    };
    ipc.song_garageband = () => opened;
    const panel = await songPanel();
    expect(panel.getByText(/out of date/)).toBeTruthy();
    await fireEvent.click(panel.getByRole('button', { name: 'Make again' }));
    expect(calls.find((c) => c.cmd === 'song_garageband')?.args).toEqual({ folder: '/lib/kad-izdzisis', transpose: -1 });
    await fireEvent.click(panel.getByRole('button', { name: 'Down a semitone' }));
    await fireEvent.click(panel.getByRole('button', { name: 'Make project' }));
    expect(calls.filter((c) => c.cmd === 'song_garageband').at(-1)?.args).toEqual({ folder: '/lib/kad-izdzisis', transpose: -1 });
  });

  it('deletes the song after asking and goes back to the Library', async () => {
    maker.installed = { version: '2026.11.08', series: 1, commit: 'abc', model: 'sw' };
    ipc.runtime_status = () => ({ installed: maker.installed, busy: false });
    ipc.default_library = () => '/m/Playalong';
    ipc.list_library = () => [];
    ipc['plugin:dialog|message'] = () => 'Move to Trash';
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: 'Open folder…' }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
    await fireEvent.click(screen.getByRole('button', { name: 'Song…' }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Delete song…' }));
    await waitFor(() =>
      expect(calls.find((c) => c.cmd === 'delete_song')?.args).toEqual({ folder: '/lib/kad-izdzisis', library: '/m/Playalong' }),
    );
    expect(await screen.findByRole('heading', { name: 'Library' })).toBeTruthy();
  });
});

describe('after the review', () => {
  function withTools() {
    maker.installed = { version: '2026.11.08', series: 1, commit: 'abc', model: 'sw' };
    ipc.runtime_status = () => ({ installed: maker.installed, busy: false });
    ipc.default_library = () => '/m/Playalong';
    ipc.list_library = () => [];
  }

  async function openSong() {
    render(Page);
    await fireEvent.click(await screen.findByRole('button', { name: /^Open (song )?folder…$/ }));
    await screen.findByRole('heading', { name: 'Kad izdzisīs' });
  }

  it('a job that finishes after leaving the song does not pull the player back to it', async () => {
    withTools();
    let finish: (v: unknown) => void = () => {};
    ipc.song_retime = () => new Promise((resolve) => (finish = resolve));
    await openSong();
    await fireEvent.click(screen.getByRole('button', { name: 'Song…' }));
    await fireEvent.click(await screen.findByRole('button', { name: 'Detect again' }));
    await fireEvent.click(screen.getByRole('button', { name: '‹ Library' }));
    await screen.findByRole('heading', { name: 'Library' });
    finish(opened);
    await settle();
    expect(calls.filter((c) => c.cmd === 'playback_open')).toHaveLength(1);
    expect(screen.getByRole('heading', { name: 'Library' })).toBeTruthy();
  });

  it('says when the mixes could not be saved', async () => {
    ipc.mixes_save = () => {
      throw "can't save the mixes: Permission denied";
    };
    await openSong();
    await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await fireEvent.input(screen.getByRole('textbox', { name: 'Name of Guide' }), { target: { value: 'Band' } });
    expect(await screen.findByText(/Permission denied/)).toBeTruthy();
  });

  it('saves a just-duplicated mix before exporting it', async () => {
    ipc.song_export = () => '/lib/kad-izdzisis/exports/kad - Guide copy.mp3';
    await openSong();
    await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    await fireEvent.click(screen.getByRole('button', { name: 'More for Guide' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: 'Duplicate' }));
    await fireEvent.click(screen.getByRole('button', { name: 'More for Guide copy' }));
    await fireEvent.click(screen.getByRole('menuitem', { name: 'Export MP3…' }));
    await waitFor(() => expect(calls.some((c) => c.cmd === 'song_export')).toBe(true));
    const order = calls.map((c) => c.cmd).filter((c) => c === 'mixes_save' || c === 'song_export');
    expect(order[0]).toBe('mixes_save');
  });
});
