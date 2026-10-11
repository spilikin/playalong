<script lang="ts">
  import { strings } from './i18n.svelte';
  import type { CountState } from './song';

  let { state, bars }: { state: CountState; bars: number } = $props();
</script>

{#if state.phase === 'count'}
  <div class="count" aria-live="assertive">
    <!-- Keyed on the click, so each one replays the pop even when two bars repeat a number. -->
    {#key state.index}
      <span class="number" class:accent={state.accent}>{state.count}</span>
    {/key}
    <span class="caption">{strings().countIn(bars)}</span>
  </div>
{/if}

<style>
  .count {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 6px;
    background: color-mix(in srgb, var(--bg) 88%, transparent);
    backdrop-filter: blur(2px);
    border-radius: 14px;
    z-index: 5;
    pointer-events: none;
  }
  .number {
    font: 800 120px/1 ui-rounded, ui-sans-serif, -apple-system, sans-serif;
    font-variant-numeric: tabular-nums;
    color: var(--ink);
    animation: pop 260ms cubic-bezier(0.2, 0.9, 0.3, 1.3);
  }
  .number.accent {
    color: var(--accent);
  }
  .caption {
    color: var(--muted);
    font-size: 13px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  @keyframes pop {
    from {
      transform: scale(1.35);
      opacity: 0.2;
    }
    to {
      transform: scale(1);
      opacity: 1;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .number {
      animation: none;
    }
  }
</style>
