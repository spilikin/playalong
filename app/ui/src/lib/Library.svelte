<script lang="ts">
  // The songs in the library, as the sidebar filters them and the toolbar's search narrows them, with the
  // song being made as the first row.
  import { convertFileSrc } from '@tauri-apps/api/core';
  import { locale, strings } from './i18n.svelte';
  import { clearJob, installTools, maker, makeSong, stopSong } from './maker.svelte';
  import { addedLabel, keyShort, megabytes, progressOf, shownSongs, timeLeft, transposeLabel, type Shelf } from './maker';

  let {
    onOpen,
    shelf = 'all',
    query = '',
    error = '',
  }: { onOpen: (folder: string) => void; shelf?: Shelf; query?: string; error?: string } = $props();

  const s = $derived(strings());
  let details = $state(false);

  const shown = $derived(shelf === 'making' ? [] : shownSongs(maker.songs, shelf, query, Date.now() / 1000));
  const job = $derived(maker.job);
  const progress = $derived(progressOf(job?.lines ?? []));
  const step = $derived(progress.step);
  const where = $derived(
    [
      step ? s.stepOf(step, s.steps[step - 1]) : '',
      progress.share !== null ? `${Math.round(progress.share * 100)}%` : '',
      progress.left !== null ? timeLeft(progress.left, s) : '',
    ]
      .filter(Boolean)
      .join(' · '),
  );

  // The log follows its newest line, as a terminal does.
  function follow(node: HTMLElement, _lines: number) {
    node.scrollTop = node.scrollHeight;
    return { update: () => (node.scrollTop = node.scrollHeight) };
  }
  const update = $derived(maker.check?.plan.runtime || maker.check?.plan.model ? maker.check : null);
  const now = new Date();
  const place = $derived(maker.library.replace(/^\/Users\/[^/]+\//, '').replaceAll('/', ' › '));

  const shortSource = (text: string) => text.replace(/^https?:\/\/(www\.)?/, '').split('/').pop() ?? text;
</script>

<div class="library">
  {#if error}<p class="error banner" role="alert">{error}</p>{/if}

  <div class="table">
    <div class="row head" aria-hidden="true">
      <span></span>
      <span>{s.columns.title}</span>
      <span>{s.columns.artist}</span>
      <span>{s.columns.key}</span>
      <span>{s.columns.bpm}</span>
      <span>{s.columns.mixes}</span>
      <span>{s.columns.added}</span>
    </div>

    {#if job}
      <div class="job" class:failed={!!job.error}>
        <div class="job-top">
          <span class="cover blank" aria-hidden="true">♪</span>
          <div class="job-what">
            <b>{job.running ? s.making : job.error ? job.error : s.done}</b>
            <span class="muted small">
              {shortSource(job.source)}
              {#if job.running}· {where} · {s.opensWhenDone}{/if}
            </span>
            {#if job.running && !details}
              <div class="track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(progress.overall * 100)}>
                <div class="fill" style:width="{Math.max(progress.overall, 0.02) * 100}%"></div>
              </div>
            {/if}
          </div>
          <div class="job-actions">
            <button onclick={() => (details = !details)}>{details ? s.hideDetails : s.details}</button>
            {#if job.running}
              <button onclick={stopSong}>{s.stop}</button>
            {:else}
              <button aria-label={s.dismiss} onclick={clearJob}>✕</button>
            {/if}
          </div>
        </div>
        {#if details}
          <ol class="steps">
            {#each s.steps as name, i (name)}
              {@const done = i + 1 < step || (!job.running && !job.error)}
              {@const now = i + 1 === step && job.running}
              <li class:done class:now>
                <span class="bar" class:busy={now && progress.share === null}>
                  <span class="fill" style:width="{done ? 100 : now ? (progress.share ?? 0) * 100 : 0}%"></span>
                </span>{name}
              </li>
            {/each}
          </ol>
          <pre class="log" use:follow={job.lines.length}>{job.lines.join('\n')}</pre>
        {/if}
      </div>
    {/if}

    {#each shown as song (song.folder)}
      <button class="row song" onclick={() => onOpen(song.folder)}>
        {#if song.cover}
          <img class="cover" src={convertFileSrc(song.cover)} alt="" />
        {:else}
          <span class="cover blank" aria-hidden="true">♪</span>
        {/if}
        <b class="title">{song.title}</b>
        <span class="muted ellipsis">{song.artist ?? ''}</span>
        <span>
          {keyShort(song.key)}
          {#each song.transposed as t (t)}<span class="shift">{transposeLabel(t, s)}</span>{/each}
        </span>
        <span>{song.bpm ? Math.round(song.bpm) : ''}</span>
        <span>{song.mixes}</span>
        <span class="muted small">{addedLabel(song.added, now, locale.lang, s)}</span>
      </button>
    {:else}
      {#if !job}<p class="empty muted">{shelf === 'making' ? s.nothingMaking : maker.songs.length ? s.noMatches : s.emptyLibrary}</p>{/if}
    {/each}
  </div>

  <footer>
    <span>{s.songsIn(place)}</span>
    {#if maker.installed}
      <span>
        {s.tools(maker.installed.version)} ·
        {#if maker.installing}
          {s.downloading}…
        {:else if update}
          <button class="link" onclick={installTools}>{s.toolsUpdate(megabytes(update.download_size))}</button>
        {:else}
          {s.upToDate}
        {/if}
      </span>
    {/if}
  </footer>
</div>

<style>
  .library {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  button:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .banner {
    margin: 8px 16px 0;
  }
  .table {
    flex: 1;
    overflow-y: auto;
  }
  .row {
    display: grid;
    grid-template-columns: 44px minmax(0, 3fr) minmax(0, 2fr) 96px 52px 56px 76px;
    gap: 12px;
    align-items: center;
    padding: 7px 16px;
    width: 100%;
    text-align: left;
    border: 0;
    border-bottom: 1px solid var(--hairline);
    border-radius: 0;
    background: none;
    font-variant-numeric: tabular-nums;
  }
  .head {
    position: sticky;
    top: 0;
    background: var(--bg);
    font-size: 12px;
    color: var(--muted);
    padding-block: 6px;
    z-index: 1;
  }
  .song:hover {
    background: var(--fill);
  }
  .cover {
    width: 36px;
    height: 36px;
    border-radius: 5px;
    object-fit: cover;
  }
  .cover.blank {
    display: grid;
    place-items: center;
    background: var(--fill);
    color: var(--muted);
  }
  .title,
  .ellipsis {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .shift {
    margin-left: 5px;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
  }
  .muted {
    color: var(--muted);
  }
  .small {
    font-size: 12px;
  }
  .empty {
    padding: 24px 16px;
  }
  .job {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 10px 16px 12px;
    background: var(--accent-soft);
    border-bottom: 1px solid var(--hairline);
  }
  .job.failed b {
    color: var(--error);
  }
  .job-top {
    display: grid;
    grid-template-columns: 44px minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
  }
  .job-what {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }
  .job-actions {
    display: flex;
    gap: 8px;
  }
  .job-actions button {
    font-size: 13px;
    padding: 4px 10px;
  }
  .track {
    height: 4px;
    border-radius: 2px;
    background: var(--fill);
    overflow: hidden;
    max-width: 360px;
  }
  .fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s;
  }
  .steps {
    margin: 0 0 0 56px;
    padding: 0;
    list-style: none;
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
  }
  .steps li {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .steps .bar {
    height: 4px;
    border-radius: 2px;
    background: var(--fill);
    overflow: hidden;
  }
  .steps .bar .fill {
    display: block;
    transition: width 0.4s;
  }
  /* A step that can't tell how far it is yet (the model loading) still shows that it's working. */
  .steps .bar.busy {
    background: linear-gradient(90deg, var(--fill) 0%, var(--accent) 50%, var(--fill) 100%) 0 0 / 200% 100%;
    animation: busy 1.4s linear infinite;
  }
  @keyframes busy {
    to {
      background-position: -200% 0;
    }
  }
  .steps .done {
    color: var(--ink);
  }
  .steps .now {
    color: var(--ink);
    font-weight: 600;
  }
  .log {
    margin: 0 0 0 56px;
    max-height: 180px;
    overflow: auto;
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--bg);
    border: 1px solid var(--hairline);
    font: 12px/1.5 ui-monospace, Menlo, monospace;
    white-space: pre-wrap;
  }
  footer {
    flex: none;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 7px 16px;
    font-size: 12px;
    color: var(--muted);
    border-top: 1px solid var(--hairline);
  }
  footer .link {
    font-size: 12px;
    color: var(--accent);
    padding: 0;
  }
</style>
