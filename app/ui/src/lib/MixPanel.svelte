<script lang="ts">
  // New mixes for the open song: presets, your own instrument levels, key, tempo, count-in and GarageBand
  // stems. It opens with what was chosen last time, for any song.
  import { strings } from './i18n.svelte';
  import { makeMixes } from './maker.svelte';
  import { transposeLabel } from './maker';
  import {
    PRESETS,
    STEMS,
    loadChoice,
    makeLabel,
    mixCount,
    mixSummary,
    saveChoice,
    type MixChoice,
    type Stem,
  } from './mixChoice';

  let { folder, onClose }: { folder: string; onClose: () => void } = $props();

  const s = $derived(strings());
  let choice = $state<MixChoice>(loadChoice());
  const count = $derived(mixCount(choice));
  // The lowest slider step means off.
  const OFF = -25;

  $effect(() => saveChoice($state.snapshot(choice)));

  function toggle(preset: string) {
    choice.presets = choice.presets.includes(preset)
      ? choice.presets.filter((p) => p !== preset)
      : PRESETS.filter((p) => p === preset || choice.presets.includes(p));
  }

  function toggleCustom() {
    choice.custom = choice.custom ? null : Object.fromEntries(STEMS.map((stem) => [stem, 0]));
  }

  function level(stem: Stem, value: number) {
    if (choice.custom) choice.custom[stem] = value <= OFF ? null : value;
  }

  const gainText = (db: number | null | undefined) =>
    db === null ? s.levelOff : `${db! > 0 ? '+' : db! < 0 ? '−' : ''}${Math.abs(db ?? 0)} dB`;

  function make() {
    void makeMixes(folder, $state.snapshot(choice), count);
    onClose();
  }
</script>

<section class="panel" aria-labelledby="mix-title">
  <div class="top">
    <h2 id="mix-title">{s.newMixes}</h2>
    <span class="muted small">{s.lastChoice}</span>
    <button class="close" aria-label={s.close} onclick={onClose}>✕</button>
  </div>

  <div class="group">
    <span class="label">{s.mixes}</span>
    <div class="chips">
      {#each PRESETS as preset (preset)}
        <button class="chip" aria-pressed={choice.presets.includes(preset)} onclick={() => toggle(preset)}>
          {s.mixNames[preset]?.[0] ?? preset}
        </button>
      {/each}
      <button class="chip" aria-pressed={!!choice.custom} onclick={toggleCustom}>{s.myMix}</button>
    </div>
  </div>

  {#if choice.custom}
    <div class="levels">
      <span class="label">{s.levels}</span>
      {#each STEMS as stem (stem)}
        <label class="level">
          <span>{s.stemNames[stem]}</span>
          <input
            type="range"
            min={OFF}
            max="6"
            step="1"
            aria-label={s.stemNames[stem]}
            value={choice.custom[stem] ?? OFF}
            oninput={(e) => level(stem, Number(e.currentTarget.value))}
          />
          <span class="muted">{gainText(choice.custom[stem])}</span>
        </label>
      {/each}
    </div>
  {/if}

  <div class="settings">
    <div class="group">
      <span class="label">{s.keyTitle}</span>
      <div class="stepper">
        <button aria-label={s.keyDown} disabled={choice.transpose <= -12} onclick={() => choice.transpose--}>−</button>
        <span>{transposeLabel(choice.transpose, s)}</span>
        <button aria-label={s.keyUp} disabled={choice.transpose >= 12} onclick={() => choice.transpose++}>+</button>
      </div>
    </div>
    <div class="group">
      <span class="label">{s.tempoTitle}</span>
      <div class="stepper">
        <button
          aria-label={s.slower}
          disabled={choice.tempo <= 0.5}
          onclick={() => (choice.tempo = Math.round(choice.tempo * 100 - 5) / 100)}>−</button
        >
        <span>{Math.round(choice.tempo * 100)}%</span>
        <button
          aria-label={s.faster}
          disabled={choice.tempo >= 1.5}
          onclick={() => (choice.tempo = Math.round(choice.tempo * 100 + 5) / 100)}>+</button
        >
      </div>
    </div>
    <fieldset class="group">
      <legend class="label">{s.countInTitle}</legend>
      <div class="segments">
        {#each [0, 1, 2] as const as bars (bars)}
          <label class:on={choice.count_in === bars}>
            <input type="radio" name="count-in" value={bars} bind:group={choice.count_in} />{s.countInBars[bars]}
          </label>
        {/each}
      </div>
    </fieldset>
  </div>

  <label class="check"><input type="checkbox" bind:checked={choice.garageband} />{s.alsoGarageBand}</label>

  <div class="grow"></div>
  <div class="bottom">
    <span class="muted small">{count ? mixSummary(choice, s) : s.chooseAMix}</span>
    <button class="primary" disabled={!count} onclick={make}>{makeLabel(choice, s)}</button>
  </div>
</section>

<style>
  .panel {
    position: fixed;
    top: var(--titlebar, 52px);
    right: 0;
    bottom: 0;
    width: min(470px, 62vw);
    box-sizing: border-box;
    z-index: 20;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px 22px;
    background: var(--bg);
    border-left: 1px solid var(--hairline);
    box-shadow: -12px 0 32px rgba(0, 0, 0, 0.12);
  }
  .top {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }
  .top .small {
    flex: 1;
  }
  h2 {
    margin: 0;
    font-size: 17px;
  }
  .close {
    width: 28px;
    height: 28px;
    padding: 0;
    border-radius: 14px;
    border: 0;
    background: var(--fill);
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    margin: 0;
    padding: 0;
    border: 0;
  }
  .label {
    padding: 0;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    font-size: 13px;
    padding: 5px 11px;
    border-radius: 14px;
  }
  .chip[aria-pressed='true'] {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--on-accent);
  }
  .levels {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 10px 12px;
    border-radius: 10px;
    background: var(--panel);
  }
  .level {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr) 56px;
    align-items: center;
    gap: 10px;
    font-size: 13px;
  }
  .level input {
    accent-color: var(--accent);
  }
  .settings {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }
  .stepper,
  .segments {
    display: flex;
    align-items: center;
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
  }
  .segments label {
    flex: 1;
    text-align: center;
    padding: 5px 0;
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
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }
  .grow {
    flex: 1;
  }
  .bottom {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .bottom .small {
    flex: 1;
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
</style>
