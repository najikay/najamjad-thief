// Board and belief heatmap.
//
// The colours come from a viridis-like ramp: colour-blind safe, and monotonic
// in lightness so the map is still readable in grayscale.

const RAMP = ['#2a3d55', '#31688e', '#21918c', '#5ec962', '#addc30', '#fde725'];

export function beliefColour(value, peak) {
  if (!value || value <= 0) return null;
  const scaled = peak > 0 ? value / peak : 0;
  const index = Math.min(RAMP.length - 1, Math.floor(scaled * RAMP.length));
  return RAMP[index];
}

export function renderBoard(node, board) {
  if (!board || !board.available) {
    node.innerHTML = '<p class="mini">Waiting for a game to start…</p>';
    return;
  }
  const size = board.size;
  const belief = board.belief || {};
  const peak = Math.max(0, ...Object.values(belief));
  const barriers = new Set((board.barriers || []).map(([r, c]) => `${r},${c}`));
  const own = (board.own_position || []).join(',');
  const hot = (board.belief_peak || []).join(',');

  node.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
  node.replaceChildren(...cells(size, { belief, peak, barriers, own, hot }));
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

function cell(key, { belief, peak, barriers, own, hot }) {
  const node = document.createElement('div');
  node.className = 'cell';
  node.title = `(${key}) belief ${(belief[key] || 0).toFixed(4)}`;
  const colour = beliefColour(belief[key], peak);
  if (colour) node.style.background = colour;
  if (barriers.has(key)) node.classList.add('barrier');
  if (key === own) {
    node.classList.add('us');
    node.textContent = 'U';
  }
  if (key === hot) node.classList.add('peak');
  return node;
}
