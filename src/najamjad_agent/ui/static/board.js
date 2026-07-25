// Board and belief heatmap.
//
// The colours come from a viridis-like ramp: colour-blind safe, and monotonic
// in lightness so the map is still readable in grayscale.

const RAMP = ['#2a3d55', '#31688e', '#21918c', '#5ec962', '#addc30', '#fde725'];

// Belief spans orders of magnitude: once the engine has a fix, a handful of
// cells hold most of the mass while the rest sit on the likelihood floor. On a
// linear value/peak scale everything but the peak collapses into one band, and
// the halo of nearly-as-likely cells around it — the part a human actually
// reads — disappears. Log scaling between the smallest and largest live values
// separates that halo while preserving order, so darker still means less
// likely. When belief is flat (nothing learned yet) there is no spread to show
// and every live cell shares one mid tone, which is the honest picture.
export function beliefScale(values) {
  const live = values.filter((value) => value > 0);
  if (!live.length) return null;
  const low = Math.log(Math.min(...live));
  const high = Math.log(Math.max(...live));
  return { low, high, flat: high - low < 1e-9 };
}

export function beliefColour(value, scale) {
  if (!scale || !value || value <= 0) return null;
  const position = scale.flat ? 0.5 : (Math.log(value) - scale.low) / (scale.high - scale.low);
  return RAMP[Math.min(RAMP.length - 1, Math.floor(position * RAMP.length))];
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

  node.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
  node.replaceChildren(...cells(size, { belief, scale, barriers, own, hot }));
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

function cell(key, { belief, scale, barriers, own, hot }) {
  const node = document.createElement('div');
  node.className = 'cell';
  node.title = `(${key}) belief ${(belief[key] || 0).toFixed(4)}`;
  const colour = beliefColour(belief[key], scale);
  if (colour) node.style.background = colour;
  if (barriers.has(key)) node.classList.add('barrier');
  if (key === own) {
    node.classList.add('us');
    node.textContent = 'U';
  }
  if (key === hot) node.classList.add('peak');
  return node;
}
