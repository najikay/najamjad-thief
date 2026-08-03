// The board: two pieces you can find, and a wash that means something.
//
// The previous version painted all 49 cells from a viridis ramp and drew us as
// a bare letter "U", so the operator's report was "I don't see a cop nor a
// thief and I can't tell which is which". Three changes, each answering part of
// that:
//
//   * pieces carry the board, not colour fills. Cop is a disc, thief a diamond,
//     so the two survive a greyscale screenshot in the report and do not rely
//     on hue;
//   * belief is drawn in the OPPONENT's colour, because belief *is* our estimate
//     of where they are — a rainbow encodes nothing. Only cells above a floor
//     are tinted, so the eye has somewhere to land;
//   * the opponent is drawn, dashed, at the belief peak. It is a guess and it
//     looks like one. Leaving them off the board entirely was what made the
//     panel unreadable: a chase with one piece on it is not a chase.
//
// Local truth only, unchanged: the dashed piece is our belief peak, never the
// opponent's true cell, which this process does not know.

// Only tint cells carrying at least this share of the peak. Below it the wash
// is noise competing with the pieces for attention.
const BELIEF_FLOOR = 0.08;

export function beliefScale(values) {
  const live = values.filter((value) => value > 0);
  if (!live.length) return null;
  const peak = Math.max(...live);
  return { peak, flat: peak - Math.min(...live) < 1e-9 };
}

// Opacity rather than a colour ramp: one hue, varying strength, so "more
// likely" reads as "more solid" without inventing a second dimension.
export function beliefAlpha(value, scale) {
  if (!scale || !value || value <= 0) return 0;
  const share = value / scale.peak;
  if (share < BELIEF_FLOOR) return 0;
  return scale.flat ? 0.35 : 0.25 + 0.55 * share;
}

function piece(role, ghost) {
  const node = document.createElement('span');
  node.className = `piece ${role}${ghost ? ' ghost' : ''}`;
  if (!ghost) node.textContent = role === 'cop' ? 'C' : 'T';
  node.title = ghost ? 'where we think they are' : 'us';
  return node;
}

export function renderBoard(node, board) {
  if (!board || !board.available) {
    node.innerHTML = '<p class="mini">Waiting for a game to start…</p>';
    return;
  }
  const size = board.size;
  const belief = board.belief || {};
  const scale = beliefScale(Object.values(belief));
  const barriers = new Set((board.barriers || []).map(([r, c]) => `${r},${c}`));
  const own = (board.own_position || []).join(',');
  const hot = (board.belief_peak || []).join(',');
  // `role` is ours; the piece we hunt is always the other one.
  const ourRole = board.role === 'police' ? 'cop' : 'thief';
  const theirRole = ourRole === 'cop' ? 'thief' : 'cop';

  node.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
  node.replaceChildren(
    ...cells(size, { belief, scale, barriers, own, hot, ourRole, theirRole })
  );
}

function cells(size, ctx) {
  const out = [];
  for (let row = 0; row < size; row += 1) {
    for (let col = 0; col < size; col += 1) {
      out.push(cell(`${row},${col}`, ctx));
    }
  }
  return out;
}

function cell(key, { belief, scale, barriers, own, hot, ourRole, theirRole }) {
  const node = document.createElement('div');
  node.className = 'cell';
  node.title = `(${key}) belief ${(belief[key] || 0).toFixed(4)}`;
  if (barriers.has(key)) {
    node.classList.add('barrier');
    return node;
  }
  const alpha = beliefAlpha(belief[key], scale);
  if (alpha > 0) {
    node.classList.add(`belief-${theirRole}`);
    node.style.setProperty('--belief', alpha.toFixed(2));
  }
  if (key === own) {
    node.classList.add('mine');
    node.append(piece(ourRole, false));
  } else if (key === hot) {
    node.append(piece(theirRole, true));
  }
  return node;
}
