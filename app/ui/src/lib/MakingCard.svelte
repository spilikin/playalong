<script lang="ts">
  // The song being made, in the player's sidebar: where it is, and Open once it's done.
  import { strings } from './i18n.svelte';
  import { clearJob, maker, stopSong } from './maker.svelte';
  import { stepOf } from './maker';

  let { onOpen }: { onOpen: (folder: string) => void } = $props();

  const s = $derived(strings());
  const job = $derived(maker.job);
  const step = $derived(job ? stepOf(job.lines) : 0);

  function openMade() {
    const folder = job?.made?.folder;
    clearJob();
    if (folder) onOpen(folder);
  }
</script>

{#if job}
  <section class="card" aria-live="polite">
    {#if job.running}
      <b>{s.making}</b>
      <div class="track"><div class="fill" style:width="{(Math.max(step - 1, 0) / 5) * 100 + 10}%"></div></div>
      <div class="row">
        <span class="muted">{step ? s.stepOf(step, s.steps[step - 1]) : ''}</span>
        <button onclick={stopSong}>{s.stop}</button>
      </div>
    {:else if job.made}
      <button class="primary" onclick={openMade}>{s.madeOpen}</button>
    {:else}
      <span class="error">{job.error}</span>
      <button onclick={clearJob}>{s.dismiss}</button>
    {/if}
  </section>
{/if}

<style>
  .card {
    margin: 8px 0;
    padding: 10px;
    border-radius: 10px;
    background: var(--bg);
    border: 1px solid var(--hairline);
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 12px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .muted {
    color: var(--muted);
  }
  button {
    font-size: 12px;
    padding: 3px 8px;
  }
  .primary {
    padding: 6px 8px;
  }
  .track {
    height: 4px;
    border-radius: 2px;
    background: var(--fill);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s;
  }
</style>
