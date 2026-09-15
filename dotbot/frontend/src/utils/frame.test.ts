import { describe, expect, test } from 'vitest';

import { siteViewport, unionAreas, viewportMarginMm } from './frame';
import { Area, Site } from '../types';

const arena: Area = { x: 0, y: 0, w: 2000, h: 2000, name: 'arena' };
const annex: Area = { x: 0, y: 2000, w: 2000, h: 2000, name: 'annex' };
const site = (extent: [number, number] | null): Site => ({
  name: 'c405-arena',
  anchor: 'the arena top-left corner',
  extent_mm: extent,
  areas: [arena, annex],
});

describe('siteViewport', () => {
  test('surrounds the site extent by the margin on every side', () => {
    expect(viewportMarginMm).toBe(2000);
    expect(siteViewport(site([2000, 4000]), [arena], arena)).toEqual({
      x: -2000, y: -2000, w: 6000, h: 8000,
    });
  });

  test('falls back to the areas shown when the site has no measured extent', () => {
    expect(siteViewport(site(null), [arena, annex], arena)).toEqual({
      x: -2000, y: -2000, w: 6000, h: 8000,
    });
  });

  test('falls back again before the controller answers', () => {
    expect(siteViewport(undefined, [], arena)).toEqual({
      x: -2000, y: -2000, w: 6000, h: 6000,
    });
  });
});

describe('unionAreas', () => {
  test('is the bounding box of its parts', () => {
    expect(unionAreas([arena, annex], arena)).toEqual({ x: 0, y: 0, w: 2000, h: 4000 });
  });

  test('is the fallback when nothing is active', () => {
    expect(unionAreas([], annex)).toEqual(annex);
  });
});
