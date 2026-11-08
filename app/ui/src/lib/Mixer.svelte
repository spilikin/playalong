<script lang="ts">
  // The mix being edited, as the song keeps playing: key, tempo, count-in, and each instrument's level,
  // mute and solo. Every change is heard at once and kept (no Save).
  import { strings } from './i18n.svelte';
  import { PRESET_IDS, STEMS, presetLevels, type Recipe } from './mixes';
  import { updateMix } from './playback.svelte';
  import type { Song } from './song';

  let { recipe, song }: { recipe: Recipe; song: Song } = $props();

  const s = $derived(strings());
  const LOWEST = -30;
  const signed = (n: number) => (n > 0 ? `+${n}` : String(n));
  const keyName = $derived(
    (recipe.transpose ? song.transpositions?.[signed(recipe.transpose)]?.key : song.key)
      ?.replace(/^([A-G])b/, '$1♭')
      .replace('#', '♯') ?? '',
  );
  const canCount = $derived(!!song.tempo && song.tempo.beat !== null);

  function change(patch: Partial<Recipe>) {
    void updateMix({ ...$state.snapshot(recipe), ...patch });
  }

  const toggle = (list: string[], stem: string) =>
    list.includes(stem) ? list.filter((x) => x !== stem) : STEMS.filter((x) => x === stem || list.includes(x));

  const gain = (db: number) => `${db > 0 ? '+' : db < 0 ? '−' : ''}${Math.abs(db)} dB`;
</script>

<section class="mixer" aria-label={s.mixer}>
  <span class="muted small">{s.mixerHint}</span>

  <div class="settings">
    <div class="field">
      <span class="label">{s.keyTitle}</span>
      <div class="stepper key">
        <button aria-label={s.keyDown} disabled={recipe.transpose <= -12} onclick={() => change({ transpose: recipe.transpose - 1 })}
          >−</button
        >
        <span>{[recipe.transpose ? signed(recipe.transpose).replace('-', '−') : '', keyName].filter(Boolean).join(' · ')}</span>
        <button aria-label={s.keyUp} disabled={recipe.transpose >= 12} onclick={() => change({ transpose: recipe.transpose + 1 })}
          >+</button
        >
      </div>
    </div>
    <div class="field">
      <span class="label">{s.tempoTitle}</span>
      <div class="stepper">
        <button
          aria-label={s.slower}
          disabled={recipe.tempo <= 0.5}
          onclick={() => change({ tempo: Math.round(recipe.tempo * 100 - 5) / 100 })}>−</button
        >
        <span>{Math.round(recipe.tempo * 100)}%{song.tempo ? ` · ${Math.round(song.tempo.bpm * recipe.tempo)} BPM` : ''}</span>
        <button
          aria-label={s.faster}
          disabled={recipe.tempo >= 1.5}
          onclick={() => change({ tempo: Math.round(recipe.tempo * 100 + 5) / 100 })}>+</button
        >
      </div>
    </div>
    <fieldset class="field" disabled={!canCount}>
      <legend class="label">{s.countInTitle}</legend>
      <div class="segments">
        {#each [0, 1, 2] as bars (bars)}
          <label class:on={canCount && recipe.count_in === bars}>
            <input
              type="radio"
              name="count-in"
              value={bars}
              checked={recipe.count_in === bars}
              disabled={!canCount}
              onchange={() => change({ count_in: bars })}
            />{s.countInBars[bars]}
          </label>
        {/each}
      </div>
      {#if !canCount}<span class="muted small">{s.countInNeedsTempo}</span>{/if}
    </fieldset>
  </div>

  <div class="stems">
    {#each STEMS as stem (stem)}
      {@const muted = recipe.mute.includes(stem)}
      {@const soloed = recipe.solo.includes(stem)}
      {@const silent = muted || (recipe.solo.length > 0 && !soloed)}
      {@const db = recipe.levels[stem] ?? 0}
      <div class="stem" class:silent>
        <b>{s.stemNames[stem]}</b>
        <input
          type="range"
          min={LOWEST}
          max="6"
          step="1"
          value={db}
          aria-label={s.stemNames[stem]}
          oninput={(e) => change({ levels: { ...recipe.levels, [stem]: Number(e.currentTarget.value) } })}
        />
        <span class="muted db">{muted ? s.levelOff : gain(db)}</span>
        <button
          class="mute"
          aria-pressed={muted}
          aria-label={s.muteStem(s.stemNames[stem])}
          onclick={() => change({ mute: toggle(recipe.mute, stem) })}>M</button
        >
        <button
          class="solo"
          aria-pressed={soloed}
          aria-label={s.soloStem(s.stemNames[stem])}
          onclick={() => change({ solo: toggle(recipe.solo, stem) })}>S</button
        >
      </div>
    {/each}
  </div>

  <div class="presets">
    <span class="muted small">{s.startFrom}</span>
    {#each PRESET_IDS as preset (preset)}
      <button onclick={() => change({ ...presetLevels(preset), solo: [] })}>{s.mixNames[preset][0]}</button>
    {/each}
  </div>
</section>

<style>
  .mixer {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px 24px 22px;
    min-height: 0;
    overflow-y: auto;
  }
  .settings {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 16px;
    padding: 12px 14px;
    border-radius: 10px;
    background: var(--panel);
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 0;
    padding: 0;
    border: 0;
    min-width: 0;
  }
  .label {
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
    width: 160px;
  }
  .stepper.key {
    width: 200px;
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
  .segments label {
    padding: 5px 10px;
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
  fieldset:disabled .segments {
    opacity: 0.45;
  }
  .stems {
    border: 1px solid var(--hairline);
    border-radius: 10px;
    overflow: hidden;
  }
  .stem {
    display: grid;
    grid-template-columns: 80px minmax(0, 1fr) 64px 32px 32px;
    gap: 10px;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid var(--hairline);
  }
  .stem:last-child {
    border-bottom: 0;
  }
  .stem b {
    font-weight: 500;
  }
  .stem.silent b,
  .stem.silent input {
    opacity: 0.45;
  }
  .stem input {
    accent-color: var(--accent);
  }
  .db {
    font-size: 13px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .mute,
  .solo {
    height: 26px;
    padding: 0;
    font-size: 12px;
    font-weight: 700;
    border-radius: 6px;
  }
  .mute[aria-pressed='true'] {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--on-accent);
  }
  .solo[aria-pressed='true'] {
    background: #f5c542;
    border-color: #d9a400;
    color: #1d1d1f;
  }
  .presets {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .presets button {
    font-size: 12px;
    padding: 3px 9px;
    border-radius: 12px;
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
</style>
