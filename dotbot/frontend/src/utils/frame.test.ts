import { describe, expect, test } from 'vitest';

import { areaFallback, siteViewport, viewportMarginMm } from './frame';
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
    expect(siteViewport(site([2000, 4000]), areaFallback)).toEqual({
      x: -2000, y: -2000, w: 6000, h: 8000,
    });
  });

  test('falls back when the site has no measured extent', () => {
    expect(siteViewport(site(null), areaFallback)).toEqual({
      x: -2000, y: -2000, w: 6000, h: 6000,
    });
  });

  test('falls back again before the controller answers', () => {
    expect(siteViewport(undefined, areaFallback)).toEqual({
      x: -2000, y: -2000, w: 6000, h: 6000,
    });
  });
});
