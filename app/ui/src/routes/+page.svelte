<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { convertFileSrc, invoke } from '@tauri-apps/api/core';
  import { getCurrentWebview } from '@tauri-apps/api/webview';
  import { open } from '@tauri-apps/plugin-dialog';
  import ChordDiagram from '$lib/ChordDiagram.svelte';
  import ChordSheet from '$lib/ChordSheet.svelte';
  import CountIn from '$lib/CountIn.svelte';
  import MixIcon from '$lib/MixIcon.svelte';
  import ThemeToggle from '$lib/ThemeToggle.svelte';
  import Wordmark from '$lib/Wordmark.svelte';
  import { strings } from '$lib/i18n.svelte';
  import {
    chordIndexAt,
    chordLabel,
    countAt,
    defaultMix,
    groupMixes,
    mixBlurb,
    mixLabel,
    mixTime,
    sheetBars,
    songTime,
    upcoming,
    type Mix,
    type OpenedSong,
  } from '$lib/song';

  const RECENTS = 'playalong.recent';
  const UPCOMING = 4;

  let opened = $state<OpenedSong | null>(null);
  let mix = $state<Mix | undefined>();
  let audio = $state<HTMLAudioElement>();
  let mixSeconds = $state(0);
  let duration = $state(0);
  let playing = $state(false);
  let error = $state('');
  let dropping = $state(false);
  let recents = $state<string[]>(loadRecents());
  let scroller = $state<HTMLElement>();
  // Song time to resume at once a newly chosen mix has loaded, so switching mixes keeps your place.
  let resumeAt: number | null = null;

  const song = $derived(opened?.song);
  const src = $derived(opened && mix ? convertFileSrc(`${opened.folder}/${mix.file}`) : '');
  const cover = $derived(opened && song?.cover ? convertFileSrc(`${opened.folder}/${song.cover.file}`) : '');
  const s = $derived(strings());
  const groups = $derived(groupMixes(song?.mixes ?? [], s));
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
      const result = await invoke<OpenedSong>('open_song', { path });
      audio?.pause();
      opened = result;
      mix = defaultMix(result.song.mixes);
      mixSeconds = 0;
      resumeAt = null;
      error = '';
      remember(path);
    } catch (e) {
      error = String(e);
    }
  }

  async function pick() {
    const chosen = await open({ directory: true, title: s.dialogTitle });
    if (typeof chosen === 'string') await openPath(chosen);
  }

  function chooseMix(choice: Mix) {
    // Compared by file: state wraps mixes in proxies, so the same mix isn't always the same object.
    if (!song || choice.file === mix?.file) return;
    resumeAt = mixSeconds > 0 ? time : null;
    mix = choice;
  }

  function loaded() {
    if (!audio || !mix || !song) return;
    duration = audio.duration;
    if (resumeAt !== null) audio.currentTime = Math.max(0, mixTime(mix, resumeAt, song));
    resumeAt = null;
    mixSeconds = audio.currentTime;
    if (playing) void audio.play();
  }

  function toggle() {
    if (!audio) return;
    if (audio.paused) void audio.play();
    else audio.pause();
  }

  function seekMix(seconds: number) {
    if (!audio) return;
    audio.currentTime = Math.min(Math.max(0, seconds), duration || seconds);
    mixSeconds = audio.currentTime;
  }

  /** Stop, back to the start of the mix (count-in included) and the top of the sheet; Play starts again. */
  async function restart() {
    audio?.pause();
    seekMix(0);
    // Jump once the sheet has redrawn for the new position: WebKit drops an animated scroll when the
    // layout changes under it, which made Restart need a second click to reach the top.
    await tick();
    scroller?.scrollTo({ top: 0, behavior: 'auto' });
  }

  function seekSong(songSeconds: number) {
    if (mix && song) seekMix(mixTime(mix, songSeconds, song));
  }

  // The audio element reports its position only a few times a second; chords and the count need every frame.
  $effect(() => {
    if (!playing || !audio) return;
    const player = audio;
    let frame = requestAnimationFrame(function tick() {
      mixSeconds = player.currentTime;
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  });

  function keys(event: KeyboardEvent) {
    if (!opened || event.target instanceof HTMLInputElement) return;
    if (event.code === 'Space') {
      event.preventDefault();
      toggle();
    } else if (event.key === 'ArrowLeft') seekMix(mixSeconds - 5);
    else if (event.key === 'ArrowRight') seekMix(mixSeconds + 5);
    else if (event.key === 'Home') restart();
    else if (/^Digit[1-4]$/.test(event.code) && !event.metaKey && !event.ctrlKey) {
      const choice = groups.main[Number(event.code.slice(5)) - 1];
      if (choice) chooseMix(choice);
    }
  }

  onMount(() => {
    let stop: (() => void) | undefined;
    let destroyed = false;
    // `Playalong <folder> [--at SECONDS]` opens that song, waiting at that point in it.
    invoke<{ path: string | null; at: number | null } | null>('launch_args')
      .then(async (launch) => {
        if (!launch?.path) return;
        await openPath(launch.path);
        if (launch.at !== null) resumeAt = launch.at;
      })
      .catch(() => {});
    getCurrentWebview()
      .onDragDropEvent((event) => {
        const p = event.payload;
        if (p.type === 'enter' || p.type === 'over') dropping = true;
        else if (p.type === 'leave') dropping = false;
        else if (p.type === 'drop') {
          dropping = false;
          if (p.paths[0]) void openPath(p.paths[0]);
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
  const folderName = (path: string) => path.split(/[\\/]/).filter(Boolean).pop() ?? path;
</script>

<svelte:window onkeydown={keys} />

{#if !opened || !song}
  <!-- The window has no title bar of its own: this strip is where it is dragged from. -->
  <div class="titlebar" data-tauri-drag-region>
    <ThemeToggle />
  </div>
  <main class="start">
    <h1>Playalong</h1>
    <Wordmark size={54} />
    <p>{s.intro}</p>
    <button class="primary" onclick={pick}>{s.openFolder}</button>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    {#if recents.length}
      <h2>{s.recent}</h2>
      <ul>
        {#each recents as path (path)}
          <li><button class="link" onclick={() => openPath(path)} title={path}>{folderName(path)}</button></li>
        {/each}
      </ul>
    {/if}
    <p class="hint">{s.dropHint}</p>
  </main>
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
        <ThemeToggle />
        <button class="open" onclick={pick}>{s.open}</button>
      </div>
    </header>

    <nav class="tray" aria-label={s.mixes}>
      {#if groups.main.length}
        <h2>{s.mixes}</h2>
        {#each groups.main as m, i (m.file)}
          {@render mixButton(m, `${mixBlurb(m, s)} (${i + 1})`)}
        {/each}
      {/if}
      {#if groups.more.length}
        <h2 class:more={groups.main.length > 0}>{s.more}</h2>
        {#each groups.more as m (m.file)}
          {@render mixButton(m, mixBlurb(m, s))}
        {/each}
      {/if}
      <div class="foot"><Wordmark /></div>
    </nav>

    <div class="main">
      {#if error}<p class="error banner" role="alert">{error}</p>{/if}
      {#if !song.mixes.length}
        <p class="banner">{s.noMixes[0]}<code>playalong mix</code>{s.noMixes[1]}</p>
      {:else if mix && mix.source_offset === null}
        <p class="banner">
          {s.oldMix[0]}<code>playalong mix</code>{s.oldMix[1]}
        </p>
      {/if}
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
    </div>
  </div>

  {#if src}
    <audio
      bind:this={audio}
      {src}
      preload="auto"
      onloadedmetadata={loaded}
      onplay={() => (playing = true)}
      onpause={() => (playing = false)}
      onended={() => (playing = false)}
      ontimeupdate={() => {
        if (audio && !playing) mixSeconds = audio.currentTime;
      }}
      onerror={() => (error = s.cantPlay(mix?.file ?? ''))}
    ></audio>
  {/if}
{/if}

{#snippet mixButton(m: Mix, hint: string)}
  <button
    class="mix"
    aria-pressed={m.file === mix?.file}
    aria-label={mixLabel(m, s)}
    title={hint}
    onclick={() => chooseMix(m)}
  >
    <span class="icon"><MixIcon name={m.name} /></span>
    <span class="label">{mixLabel(m, s)}<span class="blurb">{mixBlurb(m, s)}</span></span>
  </button>
{/snippet}

{#if dropping}
  <div class="drop" aria-hidden="true"><p>{s.drop}</p></div>
{/if}

<style>
  /* Height of the title bar row; the window buttons are placed to sit centred in it (tauri.conf.json). */
  .titlebar,
  .app {
    --titlebar: 52px;
  }
  .titlebar {
    position: fixed;
    inset: 0 0 auto;
    height: var(--titlebar);
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding: 0 14px;
    z-index: 10;
  }
  .start {
    max-width: 520px;
    margin: 14vh auto 0;
    padding: 0 24px;
  }
  .start h1 {
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 0 0 4px;
  }
  .start p {
    color: var(--muted);
    margin: 0 0 20px;
  }
  .start :global(.mark) {
    margin-bottom: 14px;
  }
  .start h2 {
    font-size: 13px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 32px 0 6px;
  }
  .start ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .start .hint {
    margin-top: 32px;
    font-size: 13px;
  }
  .primary {
    background: var(--accent);
    color: var(--on-accent);
    border-color: var(--accent);
    padding: 10px 18px;
    font-weight: 600;
  }
  .link {
    border: 0;
    padding: 4px 0;
    background: none;
    font-weight: 500;
  }
  .link:hover {
    text-decoration: underline;
  }

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
  .tray h2 {
    margin: 6px 8px 4px;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
  }
  .tray h2.more {
    margin-top: 14px;
  }
  .foot {
    margin-top: auto;
    padding: 16px 8px 0;
    opacity: 0.85;
  }
  .mix {
    display: grid;
    grid-template-columns: 26px minmax(0, 1fr);
    gap: 8px;
    align-items: center;
    width: 100%;
    text-align: left;
    border: 0;
    background: transparent;
    padding: 6px 8px;
    border-radius: 8px;
  }
  .mix:hover {
    background: var(--fill);
  }
  .mix .icon {
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    border-radius: 7px;
    background: var(--fill);
  }
  .label {
    font-size: 13px;
    font-weight: 500;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .blurb {
    display: block;
    font-size: 11px;
    font-weight: 400;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .mix[aria-pressed='true'] {
    background: var(--accent);
    color: var(--on-accent);
  }
  .mix[aria-pressed='true'] .icon {
    background: rgba(255, 255, 255, 0.22);
  }
  .mix[aria-pressed='true'] .blurb {
    color: rgba(255, 255, 255, 0.8);
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
  .error {
    color: var(--error);
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
