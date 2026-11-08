<script lang="ts">
  // The song's mixes in the sidebar. Playing: click one to hear it, keeping the place in the song. Editing
  // (Edit ↔ Done): the same rows, dragged with the mouse to reorder, and a right-click menu to rename,
  // duplicate, export or delete; + New mix at the end. The main area shows the mixer and the song meanwhile.
  import { invoke } from '@tauri-apps/api/core';
  import { tick } from 'svelte';
  import MixIcon from './MixIcon.svelte';
  import { strings } from './i18n.svelte';
  import { describeMix, newMixFrom, type Recipe } from './mixes';
  import { chooseMix, currentMix, flushSave, playback, saveMixes, updateMix } from './playback.svelte';

  let { editing = $bindable(false) }: { editing?: boolean } = $props();

  const s = $derived(strings());
  let menu = $state<{ id: string; x: number; y: number } | null>(null);
  let renaming = $state<string | null>(null);
  let draft = $state('');
  let status = $state('');
  let list = $state<HTMLElement>();
  // A press on a row becomes a drag once the mouse has moved a little; until then it's a click.
  let press: { from: number; y: number } | null = null;
  let dropAt = $state<number | null>(null);
  let dragged = false;
  const DRAG_AFTER = 4;

  function put(mixes: Recipe[]) {
    playback.mixes = mixes;
    saveMixes();
  }

  async function add(from: Recipe, at: number) {
    const copy = newMixFrom(from, playback.mixes, s);
    put([...playback.mixes.slice(0, at), copy, ...playback.mixes.slice(at)]);
    void chooseMix(copy.id);
    await startRename(copy);
  }

  function move(from: number, to: number) {
    if (from === to) return;
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

  async function startRename(m: Recipe) {
    renaming = m.id;
    draft = m.name;
    await tick();
    const field = list?.querySelector<HTMLInputElement>('input.rename');
    field?.focus();
    field?.select();
  }

  function finishRename(keep: boolean) {
    const m = playback.mixes.find((x) => x.id === renaming);
    renaming = null;
    const name = draft.trim();
    if (keep && m && name && name !== m.name) void updateMix({ ...$state.snapshot(m), name });
  }

  function openMenu(e: MouseEvent, m: Recipe) {
    if (!editing) return;
    e.preventDefault();
    menu = { id: m.id, x: e.clientX, y: e.clientY };
  }

  function act(action: (m: Recipe) => void) {
    const m = playback.mixes.find((x) => x.id === menu?.id);
    menu = null;
    if (m) action(m);
  }

  /** Where a row dropped at `y` goes: before the first row whose middle is below it. */
  function slotAt(y: number): number {
    const rows = [...(list?.querySelectorAll<HTMLElement>('[data-row]') ?? [])];
    const below = rows.findIndex((r) => {
      const box = r.getBoundingClientRect();
      return y < box.top + box.height / 2;
    });
    return below < 0 ? rows.length : below;
  }

  function pointerDown(e: PointerEvent, i: number) {
    if (!editing || e.button !== 0 || renaming) return;
    press = { from: i, y: e.clientY };
    dragged = false;
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  }

  function pointerMove(e: PointerEvent) {
    if (!press) return;
    if (!dragged && Math.abs(e.clientY - press.y) < DRAG_AFTER) return;
    dragged = true;
    dropAt = slotAt(e.clientY);
  }

  function pointerUp(e: PointerEvent) {
    if (press && dragged) {
      const slot = slotAt(e.clientY);
      move(press.from, slot > press.from ? slot - 1 : slot);
    }
    press = null;
    dropAt = null;
  }

  function choose(m: Recipe) {
    // The click that ends a drag isn't a choice.
    if (dragged) {
      dragged = false;
      return;
    }
    void chooseMix(m.id);
  }
</script>

<svelte:window onclick={() => (menu = null)} onkeydown={(e) => e.key === 'Escape' && (menu = null)} />

<div class="head">
  <h2>{s.mixes}</h2>
  <button
    class="toggle"
    aria-pressed={editing}
    onclick={() => {
      editing = !editing;
      renaming = null;
    }}
  >
    {editing ? s.done : s.editMixes}
  </button>
</div>

<div class="list" class:editing bind:this={list}>
  {#each playback.mixes as m, i (m.id)}
    {#if dropAt === i}<div class="drop-line" data-testid="drop-line"></div>{/if}
    {#if renaming === m.id}
      <div class="mix renaming" data-row>
        <span class="icon"><MixIcon name={m.id} /></span>
        <input
          class="rename"
          aria-label={s.nameOf(m.name)}
          spellcheck="false"
          bind:value={draft}
          onkeydown={(e) => {
            if (e.key === 'Enter') finishRename(true);
            else if (e.key === 'Escape') {
              e.stopPropagation();
              finishRename(false);
            }
          }}
          onblur={() => renaming === m.id && finishRename(true)}
        />
      </div>
    {:else}
      <button
        class="mix"
        data-row
        aria-pressed={m.id === playback.current}
        aria-label={`${m.name}, ${describeMix(m, s)}`}
        title={editing ? s.editHint : i < 9 ? `${describeMix(m, s)} (${i + 1})` : describeMix(m, s)}
        onclick={() => choose(m)}
        oncontextmenu={(e) => openMenu(e, m)}
        onpointerdown={(e) => pointerDown(e, i)}
        onpointermove={pointerMove}
        onpointerup={pointerUp}
      >
        <span class="icon"><MixIcon name={m.id} /></span>
        <span class="label">{m.name}<span class="blurb">{describeMix(m, s)}</span></span>
      </button>
    {/if}
  {/each}
  {#if dropAt === playback.mixes.length}<div class="drop-line" data-testid="drop-line"></div>{/if}
</div>

{#if editing}
  <button class="new" onclick={() => void add(currentMix() ?? playback.mixes[0], playback.mixes.length)}
    >{s.newMix}</button
  >
  <p class="hint">{s.editHint}</p>
{/if}
{#if menu}
  <div class="menu" role="menu" style:left="{menu.x}px" style:top="{menu.y}px">
    <button role="menuitem" onclick={() => act((m) => void startRename(m))}>{s.rename}</button>
    <button role="menuitem" onclick={() => act((m) => void add(m, playback.mixes.findIndex((x) => x.id === m.id) + 1))}
      >{s.duplicate}</button
    >
    <hr />
    <button role="menuitem" onclick={() => act((m) => void exportMix(m))}>{s.exportMp3}</button>
    <button role="menuitem" class="danger" disabled={playback.mixes.length <= 1} onclick={() => act(remove)}
      >{s.deleteMix}</button
    >
  </div>
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
  .list {
    display: flex;
    flex-direction: column;
  }
  .list.editing .mix {
    cursor: grab;
    touch-action: none;
    -webkit-user-select: none;
    user-select: none;
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
  .rename {
    font: inherit;
    font-size: 13px;
    min-width: 0;
    padding: 3px 6px;
    border: 1px solid var(--accent);
    border-radius: 5px;
    background: var(--bg);
    color: var(--ink);
  }
  .drop-line {
    height: 2px;
    margin: 1px 8px;
    border-radius: 1px;
    background: var(--accent);
  }
  .new {
    margin-top: 6px;
    text-align: left;
    padding: 6px 9px;
    border-radius: 8px;
    border: 1px dashed var(--accent);
    background: transparent;
    color: var(--accent);
    font-weight: 600;
    font-size: 13px;
  }
  .hint {
    margin: 8px 6px 0;
    font-size: 11px;
    color: var(--muted);
  }
  .menu {
    position: fixed;
    z-index: 40;
    display: flex;
    flex-direction: column;
    min-width: 160px;
    padding: 4px;
    border-radius: 8px;
    border: 1px solid var(--hairline);
    background: var(--bg);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
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
  .menu hr {
    width: 100%;
    border: 0;
    border-top: 1px solid var(--hairline);
    margin: 4px 0;
  }
  .danger {
    color: var(--error);
  }
  .status {
    margin: 8px 6px 0;
    font-size: 12px;
    color: var(--muted);
    overflow-wrap: anywhere;
  }
  .status.error {
    color: var(--error);
  }
</style>
