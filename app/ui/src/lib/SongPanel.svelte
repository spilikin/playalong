<script lang="ts">
  // What belongs to the song rather than a mix: where it starts, its tempo, its chords, its GarageBand
  // projects, and deleting it. A change of start or tempo finds chords and bars again in the background.
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { ask } from '@tauri-apps/plugin-dialog';
  import { strings } from './i18n.svelte';
  import { maker } from './maker.svelte';
  import type { OpenedSong } from './song';

  let {
    opened,
    songSeconds,
    transpose,
    onChanged,
    onDeleted,
  }: {
    opened: OpenedSong;
    /** Where the song is now, for "Set to playhead". */
    songSeconds: number;
    /** The playing mix's key change, where the GarageBand key starts. */
    transpose: number;
    onChanged: (song: OpenedSong) => Promise<void>;
    onDeleted: () => void;
  } = $props();

  const s = $derived(strings());
  const song = $derived(opened.song);
  const clock = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;

  // The fields start from the song as opened and then hold what's typed; a finished job doesn't reset them.
  let start = $state(untrack(() => clock(opened.song.song_start?.seconds ?? 0)));
  let bpm = $state(untrack(() => String(Math.round((opened.song.tempo?.bpm ?? 0) * 10) / 10 || '')));
  let key = $state(untrack(() => transpose));
  let busy = $state('');
  let error = $state('');
  let taps: number[] = [];

  /** "1:02.5" or "62.5" as seconds. */
  function seconds(text: string): number | null {
    const m = /^\s*(?:(\d+):)?(\d+(?:\.\d+)?)\s*$/.exec(text);
    return m ? Number(m[1] ?? 0) * 60 + Number(m[2]) : null;
  }

  async function job(what: string, run: () => Promise<OpenedSong>) {
    busy = what;
    error = '';
    try {
      await onChanged(await run());
    } catch (e) {
      error = String(e);
    } finally {
      busy = '';
    }
  }

  function retime(newStart: number | null, newBpm: number | null) {
    void job(s.retiming, () =>
      invoke<OpenedSong>('song_retime', { folder: opened.folder, start: newStart, bpm: newBpm }),
    );
  }

  function garageband(t: number) {
    void job(s.buildingProject, () => invoke<OpenedSong>('song_garageband', { folder: opened.folder, transpose: t }));
  }

  /** Average of the last few intervals; a pause of two seconds starts counting afresh. */
  function tap() {
    const now = performance.now();
    if (taps.length && now - taps[taps.length - 1] > 2000) taps = [];
    taps = [...taps, now].slice(-5);
    if (taps.length < 2) return;
    const gaps = taps.slice(1).map((t, i) => t - taps[i]);
    bpm = String(Math.round((60000 / (gaps.reduce((a, b) => a + b, 0) / gaps.length)) * 10) / 10);
  }

  async function remove() {
    const sure = await ask(s.deleteAsk(song.title), { kind: 'warning', okLabel: s.moveToTrash, cancelLabel: s.cancel });
    if (!sure) return;
    try {
      await invoke('delete_song', { folder: opened.folder, library: maker.library });
      onDeleted();
    } catch (e) {
      error = String(e);
    }
  }

  const signed = (n: number) => (n > 0 ? `+${n}` : String(n));
  const keyName = (t: number) =>
    ((t ? song.transpositions?.[signed(t)]?.key : song.key) ?? '').replace(/^([A-G])b/, '$1♭').replace('#', '♯');
  const keyLabel = (t: number) => [t ? signed(t).replace('-', '−') : '', keyName(t)].filter(Boolean).join(' · ');
  const projects = $derived((song.garagebands ?? []).filter((g) => g.project));
</script>

<section class="panel" aria-label={s.songPanel}>
  <div class="top">
    <h2>{s.songPanel}</h2>
    <span class="muted small">{s.songHint}</span>
  </div>

  <div class="field">
    <b>{s.songStarts}</b>
    <div class="controls">
      <input class="short" aria-label={s.songStarts} bind:value={start} disabled={!!busy} />
      <button
        disabled={!!busy || seconds(start) === null || seconds(start) === song.song_start?.seconds}
        onclick={() => retime(seconds(start), null)}>{s.setStart}</button
      >
      <button disabled={!!busy} onclick={() => ((start = clock(songSeconds)), retime(Math.round(songSeconds * 100) / 100, null))}
        >{s.setToPlayhead}</button
      >
      <span class="muted small">{s.startHint}</span>
    </div>
  </div>

  <div class="field">
    <b>BPM</b>
    <div class="controls">
      <input class="short" type="number" step="0.1" min="30" max="300" aria-label="BPM" bind:value={bpm} disabled={!!busy} />
      <button onclick={tap} disabled={!!busy}>{s.tap}</button>
      <button
        aria-label={s.setBpm}
        disabled={!!busy || !Number(bpm) || Number(bpm) === song.tempo?.bpm}
        onclick={() => retime(null, Number(bpm))}>{s.setStart}</button
      >
      {#if song.tempo?.source === 'detected'}<span class="muted small">{s.detectedBpm(song.tempo.bpm)}</span>{/if}
    </div>
  </div>

  <div class="field">
    <b>{s.chords}</b>
    <div class="controls">
      <button disabled={!!busy} onclick={() => retime(null, null)}>{s.detectAgain}</button>
      <span class="muted small">{song.key ?? ''} · {s.chordCount((song.chords ?? []).filter((c) => c.name !== 'N').length)}</span>
    </div>
  </div>

  <div class="field">
    <b>GarageBand</b>
    <div class="controls column">
      <div class="controls">
        <div class="stepper">
          <button aria-label={s.keyDown} disabled={key <= -12 || !!busy} onclick={() => key--}>−</button>
          <span>{keyLabel(key)}</span>
          <button aria-label={s.keyUp} disabled={key >= 12 || !!busy} onclick={() => key++}>+</button>
        </div>
        <button class="primary" disabled={!!busy} onclick={() => garageband(key)}>{s.makeProject}</button>
      </div>
      {#each projects as g (g.folder)}
        <div class="controls small">
          <span>{keyLabel(g.transpose)}</span>
          {#if g.outdated}
            <span class="warn">{s.outOfDate}</span>
            <button disabled={!!busy} onclick={() => garageband(g.transpose)}>{s.makeAgain}</button>
          {:else}
            <button
              class="link"
              onclick={() => void invoke('open_in_garageband', { folder: opened.folder, project: g.project }).catch(() => {})}
              >{s.openProject}</button
            >
          {/if}
        </div>
      {/each}
      <span class="muted small">{s.garageBandRow}</span>
    </div>
  </div>

  {#if busy}<p class="muted" role="status">{busy}</p>{/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}

  <div class="bottom">
    <button class="danger" disabled={!!busy} onclick={remove}>{s.deleteSong}</button>
  </div>
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 18px 26px 22px;
    min-height: 0;
    overflow-y: auto;
  }
  .top {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 8px;
  }
  h2 {
    margin: 0;
    font-size: 20px;
  }
  .field {
    display: grid;
    grid-template-columns: 150px minmax(0, 1fr);
    gap: 14px;
    align-items: start;
    padding: 12px 0;
    border-bottom: 1px solid var(--hairline);
  }
  .field b {
    font-weight: 500;
    padding-top: 5px;
  }
  .controls {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
  }
  .column {
    flex-direction: column;
    align-items: flex-start;
  }
  .controls button {
    font-size: 13px;
    padding: 5px 12px;
  }
  .short {
    width: 80px;
    font: inherit;
    padding: 4px 8px;
    border: 1px solid var(--hairline);
    border-radius: 6px;
    background: var(--bg);
    color: var(--ink);
  }
  .stepper {
    display: flex;
    align-items: center;
    width: 190px;
    border: 1px solid var(--hairline);
    border-radius: 8px;
    overflow: hidden;
    font-size: 13px;
  }
  .stepper button {
    width: 30px;
    padding: 5px 0;
    border: 0;
    border-radius: 0;
    background: none;
  }
  .stepper span {
    flex: 1;
    text-align: center;
    white-space: nowrap;
  }
  .warn {
    color: var(--error);
  }
  .bottom {
    margin-top: auto;
    padding-top: 18px;
    display: flex;
    justify-content: flex-end;
  }
  .danger {
    font-size: 13px;
    color: var(--error);
    border-color: var(--error);
  }
  button:disabled,
  input:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .muted {
    color: var(--muted);
  }
  .small {
    font-size: 12px;
  }
</style>
