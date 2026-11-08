<script lang="ts">
  // Mixes being made, in the player's sidebar. The player takes the new mixes as soon as they're done; for
  // another song than the open one, this offers to open it.
  import { strings } from './i18n.svelte';
  import { clearMixJob, maker, mixesWritten, stopSong } from './maker.svelte';

  let { openFolder, onOpen }: { openFolder: string; onOpen: (folder: string) => void } = $props();

  const s = $derived(strings());
  const job = $derived(maker.mixJob);
  const written = $derived(job ? Math.min(mixesWritten(job.lines), job.count) : 0);

  function open() {
    const folder = job?.made?.folder;
    clearMixJob();
    if (folder) onOpen(folder);
  }
</script>

{#if job && !(job.made && job.made.folder === openFolder)}
  <section class="card" aria-live="polite">
    {#if job.running}
      <b>{s.makingMixes(job.count)}</b>
      <div class="track"><div class="fill" style:width="{Math.max(written / job.count, 0.05) * 100}%"></div></div>
      <div class="row">
        <span class="muted">{s.mixesOf(written, job.count)}</span>
        <button onclick={stopSong}>{s.stop}</button>
      </div>
    {:else if job.made}
      <button class="primary" onclick={open}>{s.mixesReady}</button>
    {:else}
      <span class="error">{job.error}</span>
      <button onclick={clearMixJob}>{s.dismiss}</button>
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
