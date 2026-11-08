<script lang="ts">
  import { relaunch } from '@tauri-apps/plugin-process';
  import { strings } from './i18n.svelte';
  import { appUpdate } from './selfUpdate.svelte';
  import { maker } from './maker.svelte';

  const s = $derived(strings());
</script>

<!-- A restart would stop the song being made, so the offer waits until it's done. -->
{#if appUpdate.ready && !maker.job?.running}
  <button class="pill" title={s.appUpdateTitle(appUpdate.ready)} onclick={() => relaunch()}>{s.appUpdate}</button>
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
