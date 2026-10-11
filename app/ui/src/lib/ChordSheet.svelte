<script lang="ts">
  import { strings } from './i18n.svelte';
  import ChordDiagram from './ChordDiagram.svelte';
  import { chordLabel, indexAt, type SheetBar, type Shape } from './song';

  let {
    bars,
    shapes,
    time,
    onSeek,
    viewport,
  }: {
    bars: SheetBar[];
    shapes: Record<string, Shape>;
    time: number;
    onSeek?: (songSeconds: number) => void;
    /** The element the sheet scrolls in. */
    viewport?: HTMLElement;
  } = $props();

  const PER_LINE = 4;
  const lines = $derived(
    Array.from({ length: Math.ceil(bars.length / PER_LINE) }, (_, i) => bars.slice(i * PER_LINE, i * PER_LINE + PER_LINE)),
  );
  const currentBar = $derived(indexAt(
    bars.map((b) => b.start),
    time,
  ));
  const currentBeat = $derived.by(() => {
    const bar = bars[currentBar];
    if (!bar) return -1;
    return indexAt(
      bar.cells.map((c) => c.time),
      time,
    );
  });

  let rows: HTMLElement[] = $state([]);
  // Scroll only once the playing line has left the view, so the sheet stays put (at the top after a
  // restart, say) instead of being re-centred on every bar.
  $effect(() => {
    const row = rows[Math.floor(currentBar / PER_LINE)];
    if (!row || !viewport || typeof row.scrollIntoView !== 'function') return;
    const { top, bottom } = row.getBoundingClientRect();
    const view = viewport.getBoundingClientRect();
    if (top < view.top || bottom > view.bottom) row.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });

  const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
</script>

<section class="sheet" aria-label={strings().chordsByBar}>
  {#each lines as line, l (l)}
    <div class="row" bind:this={rows[l]}>
      <span class="num">{l * PER_LINE + 1}</span>
      {#each line as bar, b (b)}
        {@const index = l * PER_LINE + b}
        <button
          class="bar"
          class:now={index === currentBar}
          class:past={index < currentBar}
          onclick={() => onSeek?.(bar.start)}
          aria-label={strings().bar(index + 1)}
        >
          <span class="beats">
            {#each bar.cells as cell, c (c)}
              <span
                class="beat"
                class:same={cell.carried}
                class:none={cell.label === 'N.C.'}
                class:on={index === currentBar && c === currentBeat}>{chordLabel(cell.label)}</span
              >
            {/each}
          </span>
          <span class="shapes">
            {#each bar.chords as name (name)}
              <ChordDiagram {name} shape={shapes[name]} width={56} />
            {/each}
          </span>
        </button>
      {/each}
      <span class="time">{clock(line[0].start - bars[0].start)}</span>
    </div>
  {/each}
</section>

<style>
  .sheet {
    /* Chord names are lifted over their neighbouring beats; keep that stacking inside the sheet. */
    isolation: isolate;
    background: var(--panel);
    border-radius: 10px;
    padding: 6px 0;
  }
  .row {
    display: grid;
    grid-template-columns: 2.4rem repeat(4, minmax(0, 1fr)) 3.2rem;
    padding: 6px 0;
  }
  .num,
  .time {
    color: var(--muted);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    padding-top: 12px;
    text-align: center;
  }
  .bar {
    all: unset;
    position: relative;
    padding: 0 6px 4px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    cursor: pointer;
  }
  /* Every bar opens with a heavy bar line, as on a lead sheet. */
  .bar::before {
    content: '';
    position: absolute;
    left: 3px;
    top: 0;
    bottom: 0;
    width: 4px;
    border-radius: 2px;
    background: var(--barline);
  }
  .bar.now::before {
    background: var(--accent);
  }
  .bar.past .beat {
    opacity: 0.55;
  }
  .beats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 3px;
  }
  .beat {
    background: var(--cell);
    border-radius: 5px;
    min-height: 38px;
    padding: 7px 7px 0;
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.02em;
    white-space: nowrap;
    transition: background 80ms linear;
  }
  /* A name may run on over the beats that follow it; those are empty until the next change. */
  .beat:not(:empty) {
    position: relative;
    z-index: 1;
  }
  .beat.same {
    color: var(--muted);
    font-weight: 500;
  }
  .beat.none {
    color: var(--muted);
    font-size: 13px;
  }
  .beat.on {
    background: var(--accent-soft);
    box-shadow: inset 0 0 0 2px var(--accent);
    opacity: 1;
  }
  .shapes {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding-left: 2px;
  }
</style>
