<script lang="ts">
  // A sheet from the toolbar: a YouTube link or an audio file becomes a song in the library. It's made in
  // the background, as the first row of the list.
  import { open } from '@tauri-apps/plugin-dialog';
  import { untrack } from 'svelte';
  import { strings } from './i18n.svelte';
  import { maker, makeSong } from './maker.svelte';

  let { initial = '', onClose }: { initial?: string; onClose: () => void } = $props();

  const s = $derived(strings());
  let source = $state(untrack(() => initial));
  const busy = $derived(!!maker.job?.running);

  async function chooseFile() {
    const chosen = await open({
      title: s.chooseAudio,
      filters: [{ name: 'Audio', extensions: ['wav', 'mp3', 'flac', 'm4a', 'aac', 'ogg', 'opus', 'aiff', 'aif'] }],
    });
    if (typeof chosen === 'string') source = chosen;
  }

  function add(event: SubmitEvent) {
    event.preventDefault();
    if (!source.trim() || busy) return;
    void makeSong(source);
    onClose();
  }

  function focus(node: HTMLInputElement) {
    node.focus();
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onClose()} />

<div class="shade">
  <form class="sheet" aria-label={s.addSong} onsubmit={add}>
    <h2>{s.addSong}</h2>
    <label class="field">
      <span>{s.linkLabel}</span>
      <span class="row">
        <input
          aria-label={s.linkLabel}
          placeholder={s.linkPlaceholder}
          bind:value={source}
          spellcheck="false"
          autocomplete="off"
          use:focus
        />
        <button type="button" onclick={chooseFile}>{s.chooseFile}</button>
      </span>
    </label>
    <p class="muted">{busy ? s.oneAtATime : s.addSongHint}</p>
    <div class="buttons">
      <button type="button" onclick={onClose}>{s.cancel}</button>
      <button class="primary" type="submit" disabled={!source.trim() || busy}>{s.addSong}</button>
    </div>
  </form>
</div>

<style>
  .shade {
    position: absolute;
    inset: 0;
    z-index: 50;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    background: rgba(0, 0, 0, 0.18);
  }
  .sheet {
    width: min(480px, 90%);
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 20px 22px;
    border-radius: 0 0 12px 12px;
    background: var(--bg);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  }
  h2 {
    margin: 0;
    font-size: 17px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  input {
    flex: 1;
    min-width: 0;
    font: inherit;
    padding: 6px 9px;
    border-radius: 7px;
    border: 1px solid var(--hairline);
    background: var(--bg);
    color: var(--ink);
  }
  input:focus {
    border-color: var(--accent);
    outline: none;
  }
  .muted {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
  }
  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  button {
    font-size: 13px;
    padding: 6px 14px;
  }
  .primary {
    font-weight: 600;
  }
  button:disabled {
    opacity: 0.45;
    cursor: default;
  }
</style>
