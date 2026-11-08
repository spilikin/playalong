<script lang="ts">
  // The window's sidebar, on every screen: the Library's shelves, and the open song as a tree, its Song
  // item first and its mixes under it. The song keeps playing while the Library is browsed.
  import MakingCard from './MakingCard.svelte';
  import MixList from './MixList.svelte';
  import Wordmark from './Wordmark.svelte';
  import { strings } from './i18n.svelte';
  import { maker } from './maker.svelte';
  import { shownSongs, type Place } from './maker';

  let {
    place = $bindable('all'),
    songTitle = '',
    onOpen,
  }: { place?: Place; songTitle?: string; onOpen: (folder: string) => void } = $props();

  const s = $derived(strings());
  const now = Date.now() / 1000;
  const shelves = $derived(
    [
      { id: 'all' as const, label: s.allSongs, icon: '♫', count: maker.songs.length },
      { id: 'recent' as const, label: s.recentlyAdded, icon: '◷', count: shownSongs(maker.songs, 'recent', '', now).length },
      ...(maker.job ? [{ id: 'making' as const, label: s.beingMade, icon: '↻', count: maker.job.running ? 1 : 0 }] : []),
    ],
  );
</script>

<nav class="sidebar" aria-label={s.sidebar}>
  {#if maker.installed}
    <h3>{s.library}</h3>
    {#each shelves as shelf (shelf.id)}
      <button class="item" aria-pressed={place === shelf.id} onclick={() => (place = shelf.id)}>
        <span class="icon" aria-hidden="true">{shelf.icon}</span>
        <span class="name">{shelf.label}</span>
        {#if shelf.count}<span class="count">{shelf.count}</span>{/if}
      </button>
    {/each}
  {/if}

  {#if songTitle}
    <h3 title={songTitle}>{songTitle}</h3>
    <button class="item song" aria-pressed={place === 'song'} title={s.songHint} onclick={() => (place = 'song')}>
      <span class="icon" aria-hidden="true">⚙</span>
      <span class="name">{s.songPanel}</span>
      <span class="chevron" aria-hidden="true">›</span>
    </button>
    <MixList onChoose={() => (place = 'player')} />
  {/if}

  <div class="bottom">
    <!-- In the Library the song being made is the list's first row; elsewhere this card follows it. -->
    {#if place === 'player' || place === 'song'}<MakingCard {onOpen} />{/if}
    <div class="foot"><Wordmark /></div>
  </div>
</nav>

<style>
  .sidebar {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-height: 0;
    overflow-y: auto;
    padding: 0 8px 12px;
  }
  h3 {
    margin: 14px 8px 4px;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    text-align: left;
    font-size: 13px;
    padding: 5px 8px;
    border: 0;
    border-radius: 6px;
    background: transparent;
  }
  .item:hover {
    background: var(--fill);
  }
  .item[aria-pressed='true'] {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 600;
  }
  .icon {
    width: 16px;
    text-align: center;
    color: var(--accent);
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    font-size: 12px;
    color: var(--muted);
    font-weight: 400;
  }
  /* The song's own settings, set apart from its mixes below: a tinted row that leads somewhere. */
  .song {
    margin-bottom: 6px;
    background: var(--fill);
  }
  .chevron {
    color: var(--muted);
  }
  .bottom {
    margin-top: auto;
    padding-top: 12px;
  }
  .foot {
    padding: 8px 8px 0;
    opacity: 0.85;
  }
</style>
