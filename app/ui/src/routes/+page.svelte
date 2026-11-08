<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { convertFileSrc, invoke } from '@tauri-apps/api/core';
  import { getCurrentWebview } from '@tauri-apps/api/webview';
  import { open } from '@tauri-apps/plugin-dialog';
  import ChordDiagram from '$lib/ChordDiagram.svelte';
  import ChordSheet from '$lib/ChordSheet.svelte';
  import CountIn from '$lib/CountIn.svelte';
  import Library from '$lib/Library.svelte';
  import MakingCard from '$lib/MakingCard.svelte';
  import MixList from '$lib/MixList.svelte';
  import Mixer from '$lib/Mixer.svelte';
  import ThemeToggle from '$lib/ThemeToggle.svelte';
  import AppUpdate from '$lib/AppUpdate.svelte';
  import { checkAppUpdate } from '$lib/selfUpdate.svelte';
  import Welcome from '$lib/Welcome.svelte';
  import Wordmark from '$lib/Wordmark.svelte';
  import { clearJob, maker, refreshLibrary, startMaker } from '$lib/maker.svelte';
  import { liveMix } from '$lib/mixes';
  import {
    chooseMix,
    closePlayback,
    currentMix,
    openPlayback,
    pause,
    play,
    playback,
    seek,
  } from '$lib/playback.svelte';
  import { strings } from '$lib/i18n.svelte';
  import {
    chordIndexAt,
    chordLabel,
    countAt,
    forMix,
    mixTime,
    sheetBars,
    songTime,
    upcoming,
    type OpenedSong,
  } from '$lib/song';

  const RECENTS = 'playalong.recent';
  const UPCOMING = 4;

  let opened = $state<OpenedSong | null>(null);
  let error = $state('');
  let dropping = $state(false);
  let recents = $state<string[]>(loadRecents());
  let scroller = $state<HTMLElement>();
  // The mix list's Edit mode: the main area shows the mixer of the mix playing instead of the chords.
  let editing = $state(false);
  // Song time to wait at once the song is open (`--at` on the command line).
  let resumeAt: number | null = null;

  // The playing mix's timing, from its recipe and the timeline the engine gave it.
  const recipe = $derived(currentMix());
  const mix = $derived(recipe && playback.timeline ? liveMix(recipe, playback.timeline) : undefined);
  const mixSeconds = $derived(playback.mixSeconds);
  const playing = $derived(playback.playing);
  const duration = $derived(playback.duration);
  // Seen through the playing mix, so a transposed one shows its own key and chords.
  const song = $derived(opened ? forMix(opened.song, mix) : undefined);
  const cover = $derived(opened && song?.cover ? convertFileSrc(`${opened.folder}/${song.cover.file}`) : '');
  const s = $derived(strings());
  // Built as text, since Svelte drops the spaces at the edges of {#if} blocks.
  const details = $derived(
    [
      song?.artist && { before: song.artist, value: '', after: '' },
      song?.key && { before: `${s.key} `, value: song.key, after: '' },
      song?.tempo && { before: '', value: String(Math.round(song.tempo.bpm)), after: ' BPM' },
    ].filter((d) => !!d),
  );
  const time = $derived(song && mix ? songTime(mix, mixSeconds, song) : 0);
  const count = $derived(mix ? countAt(mix, mixSeconds) : ({ phase: 'song' } as const));
  const bars = $derived(song ? sheetBars(song) : []);
  const chords = $derived((song?.chords ?? []).filter((c) => c.name !== 'N'));
  const now = $derived(count.phase === 'song' ? chords[chordIndexAt(chords, time)] : undefined);
  // Before the music starts nothing is sounding yet, so the row shows the song's first chords.
  const coming = $derived(upcoming(chords, count.phase === 'song' ? time : -Infinity, UPCOMING));

  function loadRecents(): string[] {
    try {
      return JSON.parse(localStorage.getItem(RECENTS) ?? '[]');
    } catch {
      return [];
    }
  }

  function remember(path: string) {
    recents = [path, ...recents.filter((p) => p !== path)].slice(0, 6);
    try {
      localStorage.setItem(RECENTS, JSON.stringify(recents));
    } catch {
      // Recents are a convenience; blocked storage just means they aren't kept.
    }
  }

  async function openPath(path: string) {
    try {
      let result = await invoke<OpenedSong>('open_song', { path });
      // A song from before live mixes still has rendered files and no mixes of its own: the CLI brings it up
      // to date once.
      if (result.song.version < 2) {
        if (!maker.installed) throw s.needsTools;
        result = await invoke<OpenedSong>('song_refresh', { folder: result.folder });
      }
      await openPlayback(result.folder);
      editing = false;
      opened = result;
      error = '';
      remember(path);
      if (resumeAt !== null && mix && song) void seek(mixTime(mix, resumeAt, song));
      resumeAt = null;
    } catch (e) {
      error = String(e);
    }
  }

  function toLibrary() {
    void closePlayback();
    opened = null;
    error = '';
    void refreshLibrary();
  }

  // A song made while the Library is showing opens when it's done; in the player, the sidebar offers it.
  $effect(() => {
    const made = maker.job?.made;
    if (made && !opened) {
      clearJob();
      void openPath(made.folder);
    }
  });

  const AUDIO = /\.(wav|mp3|flac|m4a|aac|ogg|opus|aiff?)$/i;

  async function pick() {
    const chosen = await open({ directory: true, title: s.dialogTitle });
    if (typeof chosen === 'string') await openPath(chosen);
  }

  function toggle() {
    void (playing ? pause() : play());
  }

  function seekMix(seconds: number) {
    void seek(seconds);
  }

  /** Stop, back to the start of the mix (count-in included) and the top of the sheet; Play starts again. */
  async function restart() {
    await pause();
    await seek(0);
    // Jump once the sheet has redrawn for the new position: WebKit drops an animated scroll when the
    // layout changes under it, which made Restart need a second click to reach the top.
    await tick();
    scroller?.scrollTo({ top: 0, behavior: 'auto' });
  }

  function seekSong(songSeconds: number) {
    if (mix && song) seekMix(mixTime(mix, songSeconds, song));
  }

  function keys(event: KeyboardEvent) {
    if (!opened || event.target instanceof HTMLInputElement) return;
    if (event.code === 'Space') {
      event.preventDefault();
      toggle();
    } else if (event.key === 'ArrowLeft') seekMix(mixSeconds - 5);
    else if (event.key === 'ArrowRight') seekMix(mixSeconds + 5);
    else if (event.key === 'Home') restart();
    else if (/^Digit[1-4]$/.test(event.code) && !event.metaKey && !event.ctrlKey) {
      const choice = playback.mixes[Number(event.code.slice(5)) - 1];
      if (choice) void chooseMix(choice.id);
    }
  }

  onMount(() => {
    const started = startMaker();
    void checkAppUpdate();
    let stop: (() => void) | undefined;
    let destroyed = false;
    // `Playalong <folder> [--at SECONDS]` opens that song, waiting at that point in it. Only once the app
    // knows whether the audio tools are there: an old song needs them to be brought up to date.
    invoke<{ path: string | null; at: number | null } | null>('launch_args')
      .then(async (launch) => {
        if (!launch?.path) return;
        await started;
        resumeAt = launch.at;
        await openPath(launch.path);
      })
      .catch(() => {});
    getCurrentWebview()
      .onDragDropEvent((event) => {
        const p = event.payload;
        if (p.type === 'enter' || p.type === 'over') dropping = true;
        else if (p.type === 'leave') dropping = false;
        else if (p.type === 'drop') {
          dropping = false;
          const path = p.paths[0];
          // An audio file dropped on the Library goes into its link field, to be made into a song.
          if (path && AUDIO.test(path) && maker.installed && !opened) maker.draft = path;
          else if (path) void openPath(path);
        }
      })
      .then((unlisten) => (destroyed ? unlisten() : (stop = unlisten)))
      .catch(() => {});
    return () => {
      destroyed = true;
      stop?.();
    };
  });

  const clock = (s: number) =>
    Number.isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '0:00';
</script>

<svelte:window onkeydown={keys} />

{#if !opened || !song}
  {#if maker.installed}
    <Library onOpen={openPath} onPick={pick} {error} />
  {:else if maker.ready}
    <Welcome onPick={pick} onOpen={openPath} {recents} {error} />
  {:else}
    <div class="titlebar" data-tauri-drag-region></div>
  {/if}
{:else}
  <!-- One window-wide toolbar in the title bar, as macOS apps have it: the window buttons sit over the
       top of the mix sidebar, and the toolbar (also the drag area) fills the rest of the row. -->
  <div class="app">
    <div class="lights" data-tauri-drag-region></div>
    <header class="bar" data-tauri-drag-region>
      <div class="controls">
        <button class="restart" onclick={restart} aria-label={s.restart} title={s.restartTitle}>↺</button>
        <button class="play" onclick={toggle} aria-label={playing ? s.pause : s.play} title={s.playTitle}
          >{playing ? '❚❚' : '▶'}</button
        >
      </div>
      <div class="now" data-tauri-drag-region>
        {#if cover}
          <img class="cover" src={cover} alt={song.cover?.album ?? s.cover} title={song.cover?.album ?? undefined} />
        {:else}
          <span class="cover blank" aria-hidden="true">♪</span>
        {/if}
        <div class="info" data-tauri-drag-region>
          <div class="line" data-tauri-drag-region>
            <h1>{song.title}</h1>
            <p>
              {#each details as d, i (i)}{i ? ' · ' : ''}{d.before}<b>{d.value}</b>{d.after}{/each}
            </p>
          </div>
          <div class="scrub">
            <span class="clock">{clock(mixSeconds)}</span>
            <input
              type="range"
              min="0"
              max={duration || 0}
              step="0.1"
              value={mixSeconds}
              oninput={(e) => seekMix(Number(e.currentTarget.value))}
              aria-label={s.position}
              title="← → 5 s"
            />
            <span class="clock">-{clock(Math.max(0, duration - mixSeconds))}</span>
          </div>
        </div>
      </div>
      <div class="tools">
        <AppUpdate />
        <ThemeToggle />
        {#if maker.installed}
          <button class="open" onclick={toLibrary}>{s.backToLibrary}</button>
        {:else}
          <button class="open" onclick={pick}>{s.open}</button>
        {/if}
      </div>
    </header>

    <nav class="tray" aria-label={s.mixes}>
      <MixList bind:editing />
      <MakingCard onOpen={openPath} />
      <div class="foot"><Wordmark /></div>
    </nav>

    <div class="main">
      {#if error}<p class="error banner" role="alert">{error}</p>{/if}
      {#if editing && recipe}
        <Mixer {recipe} song={opened.song} />
      {:else}
      {#if !song.chords}
        <p class="banner">{s.noChords[0]}<code>playalong chords</code>{s.noChords[1]}</p>
      {/if}

      <section class="stage" aria-label={s.chords}>
        <figure class="current" aria-label={s.now}>
          {#if now}
            <ChordDiagram name={now.name} shape={song.chord_shapes[now.name]} width={128} />
            <figcaption>{chordLabel(now.name)}</figcaption>
          {:else}
            <span class="idle">{count.phase === 'song' && time > 0 ? 'N.C.' : '—'}</span>
          {/if}
        </figure>
        {#each coming as name, i (i)}
          <figure class="coming" aria-label={i === 0 ? s.next : undefined}>
            <ChordDiagram {name} shape={song.chord_shapes[name]} width={90} />
            <figcaption>{chordLabel(name)}</figcaption>
          </figure>
        {/each}
        <CountIn state={count} bars={mix?.count_in?.bars ?? 1} />
      </section>

      <main class="sheet-wrap" bind:this={scroller}>
        <ChordSheet {bars} shapes={song.chord_shapes} {time} onSeek={seekSong} viewport={scroller} />
      </main>
      {/if}
    </div>
  </div>
{/if}


{#if dropping}
  <div class="drop" aria-hidden="true"><p>{s.drop}</p></div>
{/if}

<style>
  .app {
    --titlebar: 52px;
  }
  /* Height of the title bar row; the window buttons are placed to sit centred in it (tauri.conf.json). */

  /* The whole window: sidebar down the left, toolbar across the top, and only the bar sheet scrolls. */
  .app {
    height: 100vh;
    display: grid;
    grid-template-columns: 184px minmax(0, 1fr);
    grid-template-rows: var(--titlebar) minmax(0, 1fr);
  }
  .lights,
  .tray {
    grid-column: 1;
    background: var(--tray);
    border-right: 1px solid var(--hairline);
  }
  .lights {
    grid-row: 1;
  }
  .bar {
    grid-row: 1;
    grid-column: 2;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 16px;
    padding: 0 14px;
    border-bottom: 1px solid var(--hairline);
    -webkit-user-select: none;
    user-select: none;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .controls button {
    display: grid;
    place-items: center;
    padding: 0;
    border-radius: 50%;
  }
  .restart {
    width: 28px;
    height: 28px;
    font-size: 15px;
    border: 0;
    background: var(--fill);
  }
  .play {
    width: 34px;
    height: 34px;
    font-size: 12px;
    background: var(--accent);
    border-color: var(--accent);
    color: var(--on-accent);
  }
  .now {
    display: grid;
    grid-template-columns: 36px minmax(0, 1fr);
    gap: 10px;
    align-items: center;
    max-width: 640px;
    width: 100%;
    justify-self: center;
    min-width: 0;
  }
  .cover {
    width: 36px;
    height: 36px;
    border-radius: 5px;
    object-fit: cover;
    box-shadow: 0 0 0 0.5px var(--hairline);
  }
  .cover.blank {
    display: grid;
    place-items: center;
    background: var(--fill);
    color: var(--muted);
  }
  .info {
    min-width: 0;
  }
  .line {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    min-width: 0;
  }
  .line h1 {
    font-size: 12px;
    font-weight: 600;
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .line p {
    margin: 0;
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: none;
    max-width: 60%;
  }
  .line p b {
    color: var(--ink);
    font-weight: 500;
  }
  .scrub {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .scrub input {
    flex: 1;
    accent-color: var(--accent);
    min-width: 0;
    height: 14px;
    margin: 0;
  }
  .clock {
    font-size: 10px;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    min-width: 30px;
  }
  .clock:last-child {
    text-align: right;
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .open {
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 7px;
    background: transparent;
  }

  .tray {
    grid-row: 2;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px 8px 12px;
    overflow-y: auto;
  }
  .foot {
    margin-top: auto;
    padding: 16px 8px 0;
    opacity: 0.85;
  }
  .main {
    grid-row: 2;
    grid-column: 2;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .banner {
    margin: 10px 16px 0;
    padding: 8px 12px;
    border-radius: 8px;
    background: var(--panel);
    color: var(--ink);
    font-size: 13px;
  }
  /* Like a chord chart app: the chord to play now large, the next ones in a row beside it. */
  .stage {
    position: relative;
    isolation: isolate;
    flex: none;
    display: flex;
    align-items: flex-start;
    gap: 22px;
    margin: 12px 16px 10px;
    padding: 10px 20px 8px;
    /* Fixed, so the sheet below doesn't shift as chords come and go. */
    height: 196px;
    overflow: hidden;
    border: 1px solid var(--hairline);
    border-radius: 12px;
  }
  figure {
    margin: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }
  figcaption {
    font-size: 18px;
    font-weight: 500;
  }
  .current figcaption {
    font-size: 26px;
    font-weight: 600;
  }
  .coming {
    padding-top: 22px;
    color: var(--muted);
  }
  .current + .coming {
    color: var(--ink);
  }
  .idle {
    width: 128px;
    padding-top: 50px;
    text-align: center;
    font-size: 34px;
    color: var(--muted);
  }
  .sheet-wrap {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0 16px 24px;
  }
  code {
    font-size: 12px;
  }
  .drop {
    position: fixed;
    inset: 12px;
    display: grid;
    place-items: center;
    border: 2px dashed var(--accent);
    border-radius: 16px;
    background: color-mix(in srgb, var(--bg) 85%, transparent);
    z-index: 30;
  }
  .drop p {
    font-size: 20px;
    font-weight: 600;
  }
</style>
