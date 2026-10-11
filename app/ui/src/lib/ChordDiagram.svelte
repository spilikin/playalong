<script lang="ts">
  import { strings } from './i18n.svelte';
  import type { Shape } from './song';

  let { name, shape, width = 100 }: { name: string; shape: Shape | undefined; width?: number } = $props();

  // A framed chord box: strings vertical (low E left), four frets down, the fret it starts at on the
  // left, muted and open strings above, a barre as a bar marked 1 on every string it frets.
  const STRING = 10;
  const FRET = 12;
  const LEFT = 18;
  const TOP = 16;
  const R = 4.4;
  const x = (string: number) => LEFT + string * STRING;
  const y = (row: number) => TOP + row * FRET;
  const mid = (fret: number) => y(fret - base + 0.5);

  const base = $derived.by(() => {
    const fretted = (shape?.frets ?? []).filter((f) => f > 0);
    return fretted.length && Math.max(...fretted) > 4 ? Math.min(...fretted) : 1;
  });
  const barre = $derived(shape?.barre ?? null);
  const underBarre = (string: number, fret: number) =>
    !!barre && fret === barre.fret && string >= barre.strings[0] && string <= barre.strings[1];
  const dots = $derived(
    (shape?.frets ?? [])
      .map((fret, string) => ({ fret, string, finger: shape?.fingers[string] ?? 0 }))
      .filter(({ fret, string }) => fret > 0 && !underBarre(string, fret)),
  );
  const barreFingers = $derived(
    (shape?.frets ?? []).map((fret, string) => string).filter((s) => underBarre(s, shape!.frets[s])),
  );
</script>

{#if shape}
  <svg
    class="dg"
    viewBox="0 0 76 80"
    {width}
    height={Math.round((width * 80) / 76)}
    role="img"
    aria-label={strings().shape(name)}
  >
    {#each [1, 2, 3] as row (row)}
      <line class="fret" x1={x(0)} y1={y(row)} x2={x(5)} y2={y(row)} />
    {/each}
    {#each [1, 2, 3, 4] as s (s)}
      <line class="string" x1={x(s)} y1={y(0)} x2={x(s)} y2={y(4)} />
    {/each}
    <rect class="frame" x={x(0)} y={y(0)} width={x(5) - x(0)} height={y(4) - y(0)} rx="2" />
    {#if base === 1}
      <line class="nut" x1={x(0)} y1={y(0)} x2={x(5)} y2={y(0)} />
    {/if}
    <text class="pos" x={x(0) - 7} y={mid(base) + 2.2}>{base}</text>
    {#each shape.frets as fret, s (s)}
      {#if fret < 0}
        <path class="mark" d="M{x(s) - 3} {y(0) - 10} l6 6 m0 -6 l-6 6" />
      {:else if fret === 0}
        <circle class="mark" cx={x(s)} cy={y(0) - 7} r="3" />
      {/if}
    {/each}
    {#if barre}
      <rect
        class="dot"
        x={x(barre.strings[0]) - R}
        y={mid(barre.fret) - R}
        width={x(barre.strings[1]) - x(barre.strings[0]) + 2 * R}
        height={2 * R}
        rx={R}
      />
      {#each barreFingers as s (s)}
        <text class="finger" x={x(s)} y={mid(barre.fret) + 2}>1</text>
      {/each}
    {/if}
    {#each dots as { fret, string, finger } (string)}
      <circle class="dot" cx={x(string)} cy={mid(fret)} r={R} />
      {#if finger}
        <text class="finger" x={x(string)} y={mid(fret) + 2}>{finger}</text>
      {/if}
    {/each}
  </svg>
{/if}

<style>
  .dg {
    display: block;
    color: var(--ink);
  }
  .frame {
    fill: none;
    stroke: currentColor;
    stroke-width: 0.9;
  }
  .string {
    stroke: currentColor;
    stroke-width: 0.7;
  }
  .fret {
    stroke: var(--fill);
    stroke-width: 2.4;
  }
  .nut {
    stroke: currentColor;
    stroke-width: 2.2;
  }
  .mark {
    fill: none;
    stroke: currentColor;
    stroke-width: 0.8;
  }
  .dot {
    fill: currentColor;
  }
  text {
    font: 500 6px ui-sans-serif, -apple-system, sans-serif;
    text-anchor: middle;
    fill: currentColor;
  }
  .finger {
    fill: var(--bg);
    font-size: 5.6px;
  }
  .pos {
    text-anchor: end;
    font-size: 6.5px;
  }
</style>
