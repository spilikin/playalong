<script lang="ts">
  // The start screen until the audio tools are in place: open a song folder, or download the tools that
  // make new songs.
  import ThemeToggle from './ThemeToggle.svelte';
  import AppUpdate from './AppUpdate.svelte';
  import { strings } from './i18n.svelte';
  import { installTools, maker } from './maker.svelte';
  import { megabytes, progressText, type Progress } from './maker';

  let {
    onPick,
    onOpen,
    recents = [],
    error = '',
  }: { onPick: () => void; onOpen: (path: string) => void; recents?: string[]; error?: string } = $props();

  const folderName = (path: string) => path.split(/[\\/]/).filter(Boolean).pop() ?? path;

  const s = $derived(strings());
  const size = $derived(maker.check ? megabytes(maker.check.download_size) : 0);
  const parts = $derived(
    [
      { stage: 'runtime' as const, label: s.toolsPart, wanted: !maker.check || !!maker.check.plan.runtime },
      { stage: 'model' as const, label: s.modelPart, wanted: !maker.check || !!maker.check.plan.model },
    ].filter((p) => p.wanted),
  );

  function state(stage: Progress['stage']): { text: string; share: number } {
    const p = maker.progress[stage];
    const later = stage === 'runtime' ? !!(maker.progress.model || maker.progress.unpack) : !!maker.progress.unpack;
    if (later) return { text: s.done, share: 1 };
    if (!p) return { text: s.waiting, share: 0 };
    return { text: progressText(p, s), share: p.total ? p.done / p.total : 0 };
  }
</script>

<div class="titlebar" data-tauri-drag-region>
  <AppUpdate />
  <ThemeToggle />
</div>
<main class="start">
  <h1 class="name">Playalong</h1>
  <p>{s.intro}</p>
  <button class="primary" onclick={onPick}>{s.openFolder}</button>
  {#if error}<p class="error" role="alert">{error}</p>{/if}

  <section class="card" aria-labelledby="setup-title">
    {#if maker.installing}
      <h2 id="setup-title">{s.downloading}</h2>
      {#each parts as part (part.stage)}
        {@const st = state(part.stage)}
        <div class="part">
          <div class="label"><span>{part.label}</span><span class="muted">{st.text}</span></div>
          <div class="track"><div class="fill" style:width="{Math.round(st.share * 100)}%"></div></div>
        </div>
      {/each}
      {#if maker.progress.unpack}<p class="muted">{s.unpacking}</p>{/if}
      <p class="muted small">{s.downloadingNote}</p>
    {:else}
      <h2 id="setup-title">{s.setupTitle}</h2>
      <p class="muted">{s.setupText}</p>
      <div class="row">
        <button class="primary" onclick={installTools}>{size ? s.setupButton(size) : s.setupButtonPlain}</button>
        <span class="muted small">{s.setupDisk}</span>
      </div>
    {/if}
    {#if maker.error}<p class="error" role="alert">{maker.error}</p>{/if}
  </section>
  {#if recents.length}
    <h2>{s.recent}</h2>
    <ul>
      {#each recents as path (path)}
        <li><button class="link" onclick={() => onOpen(path)} title={path}>{folderName(path)}</button></li>
      {/each}
    </ul>
  {/if}
  <p class="hint">{s.dropHint}</p>
</main>

<style>
  .start {
    max-width: 520px;
    margin: 14vh auto 0;
    padding: 0 24px;
  }
  .start p {
    color: var(--muted);
    margin: 0 0 20px;
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
  .name {
    margin: 0;
    font-size: 34px;
    font-weight: 700;
    letter-spacing: -0.5px;
  }
  .card {
    margin-top: 18px;
    width: min(520px, 100%);
    padding: 20px 22px;
    border-radius: 12px;
    background: var(--panel);
    display: flex;
    flex-direction: column;
    gap: 10px;
    text-align: left;
  }
  .card h2 {
    margin: 0;
    font-size: 17px;
  }
  .card p {
    margin: 0;
  }
  .muted {
    color: var(--muted);
  }
  .small {
    font-size: 13px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 4px;
  }
  .part {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .label {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
  }
  .track {
    height: 6px;
    border-radius: 3px;
    background: var(--fill);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.2s;
  }
</style>
