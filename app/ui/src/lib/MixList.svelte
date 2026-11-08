<script lang="ts">
  // The song's mixes in the sidebar. Playing: click one to hear it, keeping the place in the song. Editing
  // (Edit ↔ Done): rename in place, reorder, ⋯ for duplicate, export and delete, and + New mix; the main
  // area shows the selected mix's mixer meanwhile.
  import { invoke } from '@tauri-apps/api/core';
  import MixIcon from './MixIcon.svelte';
  import { strings } from './i18n.svelte';
  import { describeMix, newMixFrom, type Recipe } from './mixes';
  import { chooseMix, currentMix, flushSave, playback, saveMixes, updateMix } from './playback.svelte';

  let { editing = $bindable(false) }: { editing?: boolean } = $props();

  const s = $derived(strings());
  let menuFor = $state<string | null>(null);
  let dragged = $state<number | null>(null);
  let status = $state('');
  let renaming = $state<string | null>(null);

  function put(mixes: Recipe[]) {
    playback.mixes = mixes;
    saveMixes();
  }

  function add(from: Recipe, at: number) {
    const copy = newMixFrom(from, playback.mixes, s);
    put([...playback.mixes.slice(0, at), copy, ...playback.mixes.slice(at)]);
    renaming = copy.id;
    void chooseMix(copy.id);
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= playback.mixes.length || from === to) return;
    const mixes = [...playback.mixes];
    const [m] = mixes.splice(from, 1);
    mixes.splice(to, 0, m);
    put(mixes);
  }

  function remove(m: Recipe) {
    if (playback.mixes.length <= 1) return;
    const i = playback.mixes.findIndex((x) => x.id === m.id);
    const rest = playback.mixes.filter((x) => x.id !== m.id);
    put(rest);
    if (playback.current === m.id) void chooseMix(rest[Math.min(i, rest.length - 1)].id);
  }

  async function exportMix(m: Recipe) {
    status = s.exporting(m.name);
    try {
      await flushSave();
      await invoke<string>('song_export', { folder: playback.folder, mix: m.id });
      status = s.exported(m.name);
    } catch (e) {
      status = String(e);
    }
  }

  function act(action: () => void) {
    menuFor = null;
    action();
  }

  // Focuses the name of a mix just made, so it can be named straight away.
  function focusIf(node: HTMLInputElement, id: string) {
    if (renaming === id) {
      node.focus();
      node.select();
      renaming = null;
    }
  }
</script>

<svelte:window onclick={() => (menuFor = null)} onkeydown={(e) => e.key === 'Escape' && (menuFor = null)} />

<div class="head">
  <h2>{s.mixes}</h2>
  <button class="toggle" aria-pressed={editing} onclick={() => (editing = !editing)}>
    {editing ? s.done : s.editMixes}
  </button>
</div>

{#if !editing}
  {#each playback.mixes as m, i (m.id)}
    <button
      class="mix"
      aria-pressed={m.id === playback.current}
      aria-label={`${m.name}, ${describeMix(m, s)}`}
      title={i < 9 ? `${describeMix(m, s)} (${i + 1})` : describeMix(m, s)}
      onclick={() => void chooseMix(m.id)}
    >
      <span class="icon"><MixIcon name={m.id} /></span>
      <span class="label">{m.name}<span class="blurb">{describeMix(m, s)}</span></span>
    </button>
  {/each}
{:else}
  {#each playback.mixes as m, i (m.id)}
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <div
      class="row"
      class:selected={m.id === playback.current}
      class:dragging={dragged === i}
      draggable="true"
      ondragstart={() => (dragged = i)}
      ondragover={(e) => e.preventDefault()}
      ondrop={() => {
        if (dragged !== null) move(dragged, i);
        dragged = null;
      }}
      ondragend={() => (dragged = null)}
      onclick={() => void chooseMix(m.id)}
    >
      <span class="grip" aria-hidden="true">⋮⋮</span>
      <span class="fields">
        <input
          value={m.name}
          aria-label={s.nameOf(m.name)}
          spellcheck="false"
          use:focusIf={m.id}
          oninput={(e) => void updateMix({ ...$state.snapshot(m), name: e.currentTarget.value })}
        />
        <span class="blurb">{describeMix(m, s)}</span>
      </span>
      <span class="more">
        <button
          aria-label={s.moreFor(m.name)}
          aria-haspopup="menu"
          aria-expanded={menuFor === m.id}
          onclick={(e) => {
            e.stopPropagation();
            menuFor = menuFor === m.id ? null : m.id;
          }}>⋯</button
        >
        {#if menuFor === m.id}
          <div class="menu" role="menu">
            <button role="menuitem" onclick={() => act(() => add(m, i + 1))}>{s.duplicate}</button>
            <button role="menuitem" disabled={i === 0} onclick={() => act(() => move(i, i - 1))}>{s.moveUp}</button>
            <button role="menuitem" disabled={i === playback.mixes.length - 1} onclick={() => act(() => move(i, i + 1))}
              >{s.moveDown}</button
            >
            <button role="menuitem" onclick={() => act(() => void exportMix(m))}>{s.exportMp3}</button>
            <button role="menuitem" class="danger" disabled={playback.mixes.length <= 1} onclick={() => act(() => remove(m))}
              >{s.deleteMix}</button
            >
          </div>
        {/if}
      </span>
    </div>
  {/each}
  <button class="new" onclick={() => add(currentMix() ?? playback.mixes[0], playback.mixes.length)}>{s.newMix}</button>
{/if}
{#if playback.saveError}<p class="status error" role="alert">{playback.saveError}</p>{/if}
{#if status}<p class="status" role="status">{status}</p>{/if}

<style>
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 4px 6px 6px;
  }
  h2 {
    margin: 0;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  /* A pill apart from the list: it changes what the sidebar and the main area are for, not what plays. */
  .toggle {
    font-size: 12px;
    font-weight: 600;
    padding: 2px 11px;
    border-radius: 11px;
    border-color: var(--accent);
    color: var(--accent);
  }
  .toggle[aria-pressed='true'] {
    background: var(--accent);
    color: var(--on-accent);
  }
  .mix {
    display: grid;
    grid-template-columns: 26px minmax(0, 1fr);
    gap: 8px;
    align-items: center;
    width: 100%;
    text-align: left;
    border: 0;
    background: transparent;
    padding: 6px 8px;
    border-radius: 8px;
  }
  .mix:hover {
    background: var(--fill);
  }
  .mix .icon {
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    border-radius: 7px;
    background: var(--fill);
  }
  .label {
    font-size: 13px;
    font-weight: 500;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .blurb {
    display: block;
    font-size: 11px;
    font-weight: 400;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .mix[aria-pressed='true'] {
    background: var(--accent);
    color: var(--on-accent);
  }
  .mix[aria-pressed='true'] .icon {
    background: rgba(255, 255, 255, 0.22);
  }
  .mix[aria-pressed='true'] .blurb {
    color: rgba(255, 255, 255, 0.8);
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 6px;
    margin-bottom: 4px;
    border-radius: 8px;
    border: 1px solid var(--hairline);
    background: var(--bg);
  }
  .row.selected {
    border: 1.5px solid var(--accent);
  }
  .row.dragging {
    opacity: 0.5;
  }
  .grip {
    color: var(--muted);
    font-size: 12px;
    cursor: grab;
  }
  .fields {
    display: flex;
    flex-direction: column;
    min-width: 0;
    flex: 1;
  }
  .fields input {
    font: inherit;
    font-size: 13px;
    border: 0;
    padding: 0;
    background: transparent;
    color: var(--ink);
    min-width: 0;
  }
  .more {
    position: relative;
  }
  .more > button {
    border: 0;
    background: none;
    padding: 0 4px;
    color: var(--muted);
  }
  .menu {
    position: absolute;
    right: 0;
    top: 100%;
    z-index: 30;
    display: flex;
    flex-direction: column;
    min-width: 150px;
    padding: 4px;
    border-radius: 8px;
    border: 1px solid var(--hairline);
    background: var(--bg);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
  }
  .menu button {
    text-align: left;
    border: 0;
    background: none;
    font-size: 13px;
    padding: 5px 9px;
    border-radius: 5px;
  }
  .menu button:hover:not(:disabled) {
    background: var(--accent);
    color: var(--on-accent);
  }
  .menu button:disabled {
    opacity: 0.4;
  }
  .danger {
    color: var(--error);
  }
  .new {
    text-align: left;
    padding: 6px 9px;
    border-radius: 8px;
    border: 1px dashed var(--accent);
    background: transparent;
    color: var(--accent);
    font-weight: 600;
    font-size: 13px;
  }
  .status {
    margin: 8px 6px 0;
    font-size: 12px;
    color: var(--muted);
    overflow-wrap: anywhere;
  }
</style>
