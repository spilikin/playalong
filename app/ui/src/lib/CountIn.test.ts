import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import CountIn from './CountIn.svelte';

describe('CountIn', () => {
  it('shows the number of the click that just sounded, the one highlighted', () => {
    const { container } = render(CountIn, { state: { phase: 'count', count: 1, accent: true, index: 0 }, bars: 1 });
    const number = container.querySelector('.number');
    expect(number?.textContent).toBe('1');
    expect(number?.classList.contains('accent')).toBe(true);
  });

  it('is gone once the song starts', () => {
    const { container } = render(CountIn, { state: { phase: 'song' }, bars: 1 });
    expect(container.querySelector('.number')).toBeNull();
  });
});
