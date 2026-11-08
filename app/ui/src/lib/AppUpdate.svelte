<script lang="ts">
  import { strings } from './i18n.svelte';
  import { appUpdate, restartToUpdate } from './selfUpdate.svelte';
  import { maker } from './maker.svelte';

  const s = $derived(strings());
</script>

<!-- A restart would stop the song being made or the tools being installed, so the offer waits. -->
{#if appUpdate.ready && !maker.job?.running && !maker.installing}
  <button class="pill" title={s.appUpdateTitle(appUpdate.ready)} onclick={restartToUpdate}>{s.appUpdate}</button>
{/if}

<style>
  .pill {
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 0;
    background: var(--accent);
    color: var(--on-accent);
    white-space: nowrap;
  }
</style>
