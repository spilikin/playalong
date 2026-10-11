<script lang="ts">
  import '@fontsource/anton/latin-ext.css';
  import '@fontsource/anton/latin.css';

  import { toggleLanguage } from './i18n.svelte';

  let { size = 22 }: { size?: number } = $props();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
<p
  class="mark"
  style:font-size="{size}px"
  aria-label="Roks ir dzīvs!"
  onclick={(e) => {
    if (e.detail === 3) toggleLanguage();
  }}
>
  Roks ir dzīvs<span class="bang">!</span>
</p>

<style>
  .mark {
    margin: 0;
    font-family: Anton, Impact, 'Arial Narrow Bold', sans-serif;
    text-transform: uppercase;
    letter-spacing: 0.01em;
    line-height: 0.95;
    white-space: nowrap;
    color: var(--ink);
    -webkit-user-select: none;
    user-select: none;
  }
  .bang {
    color: var(--accent);
  }
</style>
