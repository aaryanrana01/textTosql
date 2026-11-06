import { describe, expect, it } from 'vitest';
import { chooseChart } from './AutoChart.jsx';

describe('chooseChart', () => {
  it('draws a line chart over a time column', () => {
    expect(chooseChart(['month', 'revenue'], [[1, 10], [2, 20], [3, 15]])).toEqual({ type: 'line', x: 0, y: 1 });
  });
  it('recognises ISO dates as time', () => {
    expect(chooseChart(['created', 'total'], [['2025-01-01', 5], ['2025-02-01', 8]])).toEqual({ type: 'line', x: 0, y: 1 });
  });
  it('draws a bar chart for text labels', () => {
    expect(chooseChart(['name', 'revenue'], [['Action', 5], ['Drama', 7]])).toEqual({ type: 'bar', x: 0, y: 1 });
  });
  it('treats id columns as labels', () => {
    expect(chooseChart(['store_id', 'count'], [[1, 526], [2, 473]])).toEqual({ type: 'bar', x: 0, y: 1 });
  });
  it('skips a single value', () => {
    expect(chooseChart(['count'], [[1000]])).toBeNull();
  });
  it('skips a single row', () => {
    expect(chooseChart(['name', 'revenue'], [['Action', 5]])).toBeNull();
  });
  it('skips results too large to chart clearly', () => {
    const rows = Array.from({ length: 61 }, (_, i) => [`item ${i}`, i]);
    expect(chooseChart(['name', 'value'], rows)).toBeNull();
  });
  it('skips results with no numbers', () => {
    expect(chooseChart(['first_name', 'last_name'], [['A', 'B'], ['C', 'D']])).toBeNull();
  });
});
