<script lang="ts">
  let { name }: { name: string } = $props();

  // Line icons on a 24 grid in the SF Symbols manner: what the mix leaves you to play or hear.
  const GUITAR =
    'M14.5 9.5l5-5 M18 3l3 3 M13.6 10.4a3.5 3.5 0 0 0-5.1-.6l-.6.6a3 3 0 0 1-2.2.9A3.2 3.2 0 0 0 3 14.5c0 3.6 2.9 6.5 6.5 6.5a3.2 3.2 0 0 0 3.2-2.7 3 3 0 0 1 .9-2.2l.6-.6a3.5 3.5 0 0 0-.6-5.1z';
  const SOUNDHOLE = 'M11.3 14a1.3 1.3 0 1 1-2.6 0 1.3 1.3 0 0 1 2.6 0z';
  const PATHS: Record<string, { d: string; faint?: boolean }[]> = {
    original: [{ d: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z M14.5 12a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z M12 5.5a6.5 6.5 0 0 1 6.5 6.5' }],
    guide: [{ d: `${GUITAR} ${SOUNDHOLE}`, faint: true }],
    'no-guitar': [{ d: `${GUITAR} ${SOUNDHOLE}` }, { d: 'M3 3l18 18' }],
    'guitar-only': [{ d: `${GUITAR} ${SOUNDHOLE}` }],
    'vocals-only': [{ d: 'M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z M5.5 11a6.5 6.5 0 0 0 13 0 M12 17.5V21 M8.5 21h7' }],
    backing: [{ d: 'M20 8c0 1.7-3.6 3-8 3s-8-1.3-8-3 3.6-3 8-3 8 1.3 8 3z M4 8v8c0 1.7 3.6 3 8 3s8-1.3 8-3V8' }],
    'rhythm-section': [{ d: 'M20 8c0 1.7-3.6 3-8 3s-8-1.3-8-3 3.6-3 8-3 8 1.3 8 3z M4 8v8c0 1.7 3.6 3 8 3s8-1.3 8-3V8' }],
    'drums-only': [{ d: 'M4 20l8-10 M20 20l-8-10 M14 8a2 2 0 1 1-4 0 2 2 0 0 1 4 0z' }],
  };
  const FALLBACK = [{ d: 'M3 12h2 M7 8v8 M11 5v14 M15 9v6 M19 11v2' }];
  const parts = $derived(PATHS[name] ?? FALLBACK);
</script>

<svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
  {#each parts as part, i (i)}
    <path d={part.d} opacity={part.faint ? 0.45 : 1} />
  {/each}
</svg>

<style>
  svg {
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
    flex: none;
  }
</style>
