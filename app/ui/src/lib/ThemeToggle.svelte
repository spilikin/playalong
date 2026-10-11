<script lang="ts">
  import { strings } from './i18n.svelte';
  import { onMount } from 'svelte';
  import { applyTheme, storedTheme, type ThemeChoice } from './theme';

  let choice = $state<ThemeChoice>(storedTheme());
  let systemDark = $state(false);
  const dark = $derived(choice === 'system' ? systemDark : choice === 'dark');

  onMount(() => {
    void applyTheme(choice);
    // Until toggled the app follows the system, so the icon has to follow it too.
    const query = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!query) return;
    systemDark = query.matches;
    const changed = (e: MediaQueryListEvent) => (systemDark = e.matches);
    query.addEventListener('change', changed);
    return () => query.removeEventListener('change', changed);
  });

  function toggle() {
    choice = dark ? 'light' : 'dark';
    void applyTheme(choice);
  }
</script>

<button class="toggle" onclick={toggle} aria-label={dark ? strings().light : strings().dark} title={strings().themeTitle}>
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
    {#if dark}
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    {:else}
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    {/if}
  </svg>
</button>

<style>
  .toggle {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: 0;
    border-radius: 7px;
    background: transparent;
  }
  .toggle:hover {
    background: var(--fill);
  }
  svg {
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
</style>
