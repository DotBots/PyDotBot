// One distinct target per bot, by squared distance. The fake world's half of
// what `assign_targets` does in the demos' Python helper.

/** Interleaved x, y pairs: the shape every target set travels in. */
export type Points = Float64Array;

function costTo(px: number, py: number, targets: Points, t: number): number {
  const dx = targets[t * 2] - px;
  const dy = targets[t * 2 + 1] - py;
  return dx * dx + dy * dy;
}

/**
 * Nearest free target per source, taken in source order.
 *
 * The globally-nearest-pair greedy the Python uses costs a full scan per
 * source picked; this one costs a scan of what is still free, so a thousand
 * sources on a thousand targets is half a million distance tests rather than
 * a billion. The crossings it leaves behind are what the swap passes are for.
 */
function greedy(sources: Points, targets: Points, assign: Int32Array): void {
  const n = assign.length;
  const m = targets.length >> 1;
  const free = new Int32Array(m);
  for (let i = 0; i < m; i++) free[i] = i;
  let remaining = m;

  for (let i = 0; i < n; i++) {
    const px = sources[i * 2];
    const py = sources[i * 2 + 1];
    let best = 0;
    let bestCost = Infinity;
    for (let k = 0; k < remaining; k++) {
      const c = costTo(px, py, targets, free[k]);
      if (c < bestCost) {
        bestCost = c;
        best = k;
      }
    }
    assign[i] = free[best];
    free[best] = free[--remaining];
  }
}

/**
 * Exchange the targets of two bots while that shortens the pair.
 *
 * Every crossing greedy leaves - the bot served early taking a target a later
 * one was much closer to - is one exchange away from being gone. A pass that
 * changes nothing ends the search.
 */
function swapPasses(
  sources: Points,
  targets: Points,
  assign: Int32Array,
  maxPasses: number,
): void {
  const n = assign.length;
  for (let pass = 0; pass < maxPasses; pass++) {
    let swaps = 0;
    for (let i = 0; i < n; i++) {
      const ax = sources[i * 2];
      const ay = sources[i * 2 + 1];
      let ti = assign[i];
      let heldA = costTo(ax, ay, targets, ti);
      for (let j = i + 1; j < n; j++) {
        const bx = sources[j * 2];
        const by = sources[j * 2 + 1];
        const tj = assign[j];
        const gain =
          heldA +
          costTo(bx, by, targets, tj) -
          costTo(ax, ay, targets, tj) -
          costTo(bx, by, targets, ti);
        if (gain > 1e-9) {
          assign[i] = tj;
          assign[j] = ti;
          ti = tj;
          heldA = costTo(ax, ay, targets, ti);
          swaps++;
        }
      }
    }
    if (swaps === 0) break;
  }
}

/**
 * A target index per source, in source order, no two the same. There must be
 * at least as many targets as sources.
 */
export function assignTargets(sources: Points, targets: Points, maxPasses = 6): Int32Array {
  const n = sources.length >> 1;
  const m = targets.length >> 1;
  const assign = new Int32Array(n);
  if (n === 0) return assign;
  if (m < n) throw new Error(`${n} sources need ${n} targets, got ${m}`);
  greedy(sources, targets, assign);
  swapPasses(sources, targets, assign, maxPasses);
  return assign;
}

/** The assigned targets themselves, laid out per source. */
export function gather(targets: Points, assign: Int32Array): Points {
  const out = new Float64Array(assign.length * 2);
  for (let i = 0; i < assign.length; i++) {
    out[i * 2] = targets[assign[i] * 2];
    out[i * 2 + 1] = targets[assign[i] * 2 + 1];
  }
  return out;
}

/** Points from a list of pairs, which is how a test and a message state them. */
export function toPoints(pairs: { x: number; y: number }[]): Points {
  const out = new Float64Array(pairs.length * 2);
  pairs.forEach((p, i) => {
    out[i * 2] = p.x;
    out[i * 2 + 1] = p.y;
  });
  return out;
}
