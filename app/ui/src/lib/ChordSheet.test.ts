import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import ChordSheet from './ChordSheet.svelte';
import { song } from './fixture';
import { sheetBars } from './song';

describe('ChordSheet', () => {
  it('lights the beat that is playing and marks its bar', () => {
    const { container } = render(ChordSheet, { bars: sheetBars(song), shapes: song.chord_shapes, time: 23.4 });
    const on = container.querySelectorAll('.beat.on');
    expect(on).toHaveLength(1);
    expect(on[0].textContent).toBe('A♭'); // the third beat of bar 1, where Ab comes in
    expect(container.querySelector('.bar.now')?.getAttribute('aria-label')).toBe('Bar 1');
  });

  it('shows the shapes of every chord in each bar', () => {
    render(ChordSheet, { bars: sheetBars(song), shapes: song.chord_shapes, time: 0 });
    expect(screen.getAllByRole('img', { name: 'Bbm chord shape' })).toHaveLength(1);
    expect(screen.getAllByRole('img', { name: 'Ab chord shape' })).toHaveLength(2);
  });

  it('seeks to a bar when it is clicked', async () => {
    const onSeek = vi.fn();
    render(ChordSheet, { bars: sheetBars(song), shapes: song.chord_shapes, time: 0, onSeek });
    await fireEvent.click(screen.getByRole('button', { name: 'Bar 2' }));
    expect(onSeek).toHaveBeenCalledWith(24.25);
  });
});

describe('following the song', () => {
  it('leaves the sheet alone while the playing line is in view, and scrolls once it leaves', async () => {
    const bars = sheetBars(song);
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    Element.prototype.getBoundingClientRect = () => ({ top: 400, bottom: 500 }) as DOMRect;
    const viewport = document.createElement('div');
    viewport.getBoundingClientRect = () => ({ top: 250, bottom: 800 }) as DOMRect;
    const props = { bars, shapes: song.chord_shapes, viewport };
    const { rerender, container } = render(ChordSheet, { ...props, time: 22.3 });
    expect(scrolled).not.toHaveBeenCalled();

    const row = container.querySelector('.row') as HTMLElement;
    row.getBoundingClientRect = () => ({ top: 2000, bottom: 2100 }) as DOMRect;
    await rerender({ ...props, time: 24.3 });
    expect(scrolled).toHaveBeenCalled();
  });
});
