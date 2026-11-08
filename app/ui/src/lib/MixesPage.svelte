<script lang="ts">
  // The open song's mixes, one version (key and tempo) at a time: what it has, and what to make. It starts at
  // the version of the mix that's playing; which rows are ticked is remembered for every song.
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { strings } from './i18n.svelte';
  import { keyShort } from './maker';
  import { maker, makeMixes } from './maker.svelte';
  import { MY_MIX, PRESETS, STEMS, loadPicks, savePicks, toChoice, toMake, type Picks, type Stem } from './mixChoice';
  import { madeIn, transposeKey, versionsOf } from './mixVersions';
  import type { Mix, Song } from './song';

  let {
    song,
    folder,
    playing,
    onPlay,
    onClose,
  }: { song: Song; folder: string; playing?: Mix; onPlay: (mix: Mix) => void; onClose: () => void } = $props();

  const s = $derived(strings());
  // The lowest slider step means off.
  const OFF = -25;

  // Starts at the playing mix's version; picking another mix to hear afterwards doesn't move the page.
  let transpose = $state(untrack(() => playing?.transpose ?? 0));
  let tempo = $state(untrack(() => playing?.tempo ?? 1));
  let picks = $state<Picks>(loadPicks());
  let levelsOpen = $state(false);

  $effect(() => savePicks($state.snapshot(picks)));

  const versions = $derived(versionsOf(song));
  const made = $derived(madeIn(song, transpose, tempo));
  const mine = $derived(made.mixes.get(MY_MIX));
  const making = $derived(toMake(picks, made, s));
  const busy = $derived(!!maker.mixJob?.running || !!maker.job?.running);
  const keyName = $derived(song.key ? transposeKey(song.key, transpose) : '');
  const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '');
  const versionName = (t: number, pace: number) =>
    `${song.key ? keyShort(transposeKey(song.key, t)) : signed(t) || s.originalKey} · ${Math.round(pace * 100)}%`;

  function tick(preset: string) {
    picks.presets = picks.presets.includes(preset)
      ? picks.presets.filter((p) => p !== preset)
      : PRESETS.filter((p) => p === preset || picks.presets.includes(p));
  }

  function level(stem: Stem, value: number) {
    picks.levels[stem] = value <= OFF ? null : value;
  }

  const gainText = (db: number | null) =>
    db === null ? s.levelOff : `${db > 0 ? '+' : db < 0 ? '−' : ''}${Math.abs(db)} dB`;
  const levelsText = $derived(
    STEMS.filter((stem) => picks.levels[stem] !== 0)
      .map((stem) => `${s.stemNames[stem].toLowerCase()} ${gainText(picks.levels[stem])}`)
      .join(', ') || s.asRecorded,
  );

  function make() {
    const choice = toChoice($state.snapshot(picks), made, transpose, tempo);
    void makeMixes(folder, choice, making.length);
  }
</script>

{#snippet status(mix: Mix | undefined, wanted: boolean)}
  {#if mix}
    <span class="made">
      {s.madeLabel} ·
      {#if mix.file === playing?.file}{s.playingLabel}{:else}<button class="link" onclick={() => onPlay(mix)}
          >{s.playLabel}</button
        >{/if}
    </span>
  {:else if wanted}
    <span class="will">{s.willMake}</span>
  {:else}
    <span></span>
  {/if}
{/snippet}

<section class="page" aria-labelledby="mixes-title">
  <div class="top">
    <button onclick={onClose}>{s.backToChords}</button>
    <h2 id="mixes-title">{s.mixes}</h2>
  </div>

  <div class="versions">
    <span class="muted">{s.songHas}</span>
    {#each versions as v (`${v.transpose}@${v.tempo}`)}
      <button
        class="chip"
        aria-pressed={v.transpose === transpose && v.tempo === tempo}
        onclick={() => ((transpose = v.transpose), (tempo = v.tempo))}
      >
        {versionName(v.transpose, v.tempo)} · {s.mixCount(v.mixes)}{v.garageband ? ' + GarageBand' : ''}
      </button>
    {/each}
  </div>

  <div class="version">
    <div class="field">
      <span class="label">{s.keyTitle}</span>
      <div class="stepper key">
        <button aria-label={s.keyDown} disabled={transpose <= -12} onclick={() => transpose--}>−</button>
        <span>{[signed(transpose), keyName.replace(/^([A-G])b/, '$1♭').replace('#', '♯')].filter(Boolean).join(' · ')}</span>
        <button aria-label={s.keyUp} disabled={transpose >= 12} onclick={() => transpose++}>+</button>
      </div>
    </div>
    <div class="field">
      <span class="label">{s.tempoTitle}</span>
      <div class="stepper">
        <button aria-label={s.slower} disabled={tempo <= 0.5} onclick={() => (tempo = Math.round(tempo * 100 - 5) / 100)}
          >−</button
        >
        <span>{Math.round(tempo * 100)}%{song.tempo ? ` · ${Math.round(song.tempo.bpm * tempo)}` : ''}</span>
        <button aria-label={s.faster} disabled={tempo >= 1.5} onclick={() => (tempo = Math.round(tempo * 100 + 5) / 100)}
          >+</button
        >
      </div>
    </div>
    <p class="muted small">{s.versionHint}</p>
  </div>

  <div class="rows" role="group" aria-label={s.mixes}>
    {#each PRESETS as preset (preset)}
      {@const mix = made.mixes.get(preset)}
      <div class="row" class:is-made={!!mix}>
        {#if mix}
          <span class="tick" aria-hidden="true">✓</span>
        {:else}
          <input type="checkbox" checked={picks.presets.includes(preset)} onchange={() => tick(preset)} aria-label={s.mixNames[preset][0]} />
        {/if}
        <b>{s.mixNames[preset][0]}</b>
        <span class="muted small">{s.mixNames[preset][1]}</span>
        {@render status(mix, picks.presets.includes(preset))}
      </div>
    {/each}

    <div class="row" class:is-made={!!mine}>
      {#if mine}
        <span class="tick" aria-hidden="true">✓</span>
      {:else}
        <input type="checkbox" bind:checked={picks.myMix} aria-label={s.myMix} />
      {/if}
      <b>{s.myMix}</b>
      <span class="muted small">
        {levelsText} ·
        <button class="link" aria-expanded={levelsOpen} onclick={() => (levelsOpen = !levelsOpen)}>{s.levelsButton}</button>
      </span>
      {@render status(mine, picks.myMix)}
    </div>
    {#if levelsOpen}
      <div class="levels">
        {#each STEMS as stem (stem)}
          <label class="level">
            <span>{s.stemNames[stem]}</span>
            <input
              type="range"
              min={OFF}
              max="6"
              step="1"
              aria-label={s.stemNames[stem]}
              value={picks.levels[stem] ?? OFF}
              oninput={(e) => level(stem, Number(e.currentTarget.value))}
            />
            <span class="muted">{gainText(picks.levels[stem])}</span>
          </label>
        {/each}
      </div>
    {/if}

    <div class="row" class:is-made={!!made.garageband}>
      {#if made.garageband}
        <span class="tick" aria-hidden="true">✓</span>
      {:else}
        <input type="checkbox" bind:checked={picks.garageband} aria-label={s.garageBandProject} />
      {/if}
      <b>{s.garageBandProject}</b>
      <span class="muted small">{s.garageBandRow}</span>
      {#if made.garageband}
        {@const project = made.garageband}
        <span class="made">
          {s.madeLabel} ·
          <button class="link" onclick={() => invoke('open_in_garageband', { folder, project }).catch(() => {})}
            >{s.openInGarageBand}</button
          >
        </span>
      {:else if picks.garageband}
        <span class="will">{s.willMake}</span>
      {:else}
        <span></span>
      {/if}
    </div>
  </div>

  <div class="bottom">
    <fieldset class="count">
      <legend>{s.countInTitle}</legend>
      <div class="segments">
        {#each [0, 1, 2] as const as bars (bars)}
          <label class:on={picks.count_in === bars}>
            <input type="radio" name="count-in" value={bars} bind:group={picks.count_in} />{s.countInBars[bars]}
          </label>
        {/each}
      </div>
    </fieldset>
    <span class="muted small summary">
      {making.length ? `${s.forVersion(versionName(transpose, tempo))} ${making.join(', ')}` : s.nothingToMake}
    </span>
    <button class="primary" disabled={!making.length || busy} onclick={make}>{s.makeN(making.length)}</button>
  </div>
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px 26px 22px;
    min-height: 0;
    overflow-y: auto;
  }
  .top {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .top button {
    font-size: 13px;
    padding: 5px 10px;
  }
  h2 {
    margin: 0;
    font-size: 20px;
  }
  .versions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }
  .chip {
    font-size: 13px;
    padding: 4px 10px;
    border-radius: 14px;
  }
  .chip[aria-pressed='true'] {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--on-accent);
  }
  .version {
    display: flex;
    align-items: flex-end;
    flex-wrap: wrap;
    gap: 16px;
    padding: 12px 14px;
    border-radius: 10px;
    background: var(--panel);
  }
  .version p {
    margin: 0 0 6px;
    flex: 1;
    min-width: 200px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .label,
  legend {
    padding: 0;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .stepper,
  .segments {
    display: flex;
    align-items: center;
    border: 1px solid var(--hairline);
    border-radius: 8px;
    overflow: hidden;
    background: var(--bg);
    font-size: 13px;
  }
  .stepper {
    width: 140px;
  }
  .stepper.key {
    width: 190px;
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
  .rows {
    display: flex;
    flex-direction: column;
    border: 1px solid var(--hairline);
    border-radius: 10px;
    overflow: hidden;
  }
  .row {
    display: grid;
    grid-template-columns: 26px 150px minmax(0, 1fr) 130px;
    gap: 10px;
    align-items: center;
    padding: 7px 12px;
    border-bottom: 1px solid var(--hairline);
    font-size: 14px;
  }
  .row:last-child {
    border-bottom: 0;
  }
  .row b {
    font-weight: 500;
  }
  .row input {
    accent-color: var(--accent);
    justify-self: center;
  }
  .is-made {
    background: var(--made-soft, rgba(52, 199, 89, 0.07));
  }
  .tick {
    text-align: center;
    color: var(--made, #248a3d);
  }
  .made {
    font-size: 12px;
    color: var(--made, #248a3d);
  }
  .will {
    font-size: 12px;
    color: var(--accent);
  }
  .levels {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 12px 10px 48px;
    background: var(--panel);
    border-bottom: 1px solid var(--hairline);
  }
  .level {
    display: grid;
    grid-template-columns: 70px minmax(0, 260px) 56px;
    align-items: center;
    gap: 10px;
    font-size: 13px;
  }
  .level input {
    accent-color: var(--accent);
  }
  .bottom {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: auto;
  }
  .count {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0;
    padding: 0;
    border: 0;
  }
  .count legend {
    float: left;
    margin-right: 8px;
  }
  .segments label {
    padding: 4px 10px;
    cursor: pointer;
  }
  .segments label.on {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 600;
  }
  .segments input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .segments label:has(input:focus-visible) {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }
  .summary {
    flex: 1;
    text-align: right;
  }
  .primary {
    padding: 8px 16px;
    font-weight: 600;
  }
  button:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .muted {
    color: var(--muted);
  }
  .small {
    font-size: 12px;
  }
  .link {
    font-size: inherit;
    padding: 0;
    border: 0;
    background: none;
    color: var(--accent);
  }
</style>
