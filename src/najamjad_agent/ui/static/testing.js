// The manual-testing panel: which mode we are in, and who is answering.
//
// Two things an operator keeps re-deriving from logs, put on the page:
//
//   * practice mode  — can this run reach the lecturer at all?
//   * liveness       — is anything listening on our URL, and on theirs?
//
// Both render from what the server returns, never from what the click asked
// for. A toggle that painted itself "on" optimistically would be lying about
// exactly the setting whose whole job is to be trustworthy.

const OFF = 'not configured';

export function renderPractice(node, practice, enabled) {
  const on = Boolean(practice && practice.enabled);
  node.className = on ? 'practice on' : 'practice';
  const target = on ? practice.redirect_to : 'the lecturer';
  node.innerHTML = `
    <div class="row">
      <span>Mode</span>
      <strong>${on ? 'PRACTICE' : 'COUNTED'}</strong>
    </div>
    <div class="row"><span>Reports go to</span><strong>${target}</strong></div>`;

  const button = document.createElement('button');
  button.textContent = on ? 'Switch to counted' : 'Switch to practice';
  button.disabled = !enabled;
  button.title = enabled
    ? 'Writes config/setup.json; takes effect on the next report'
    : 'Controls are disabled — set features.controls in config/setup.json';
  button.dataset.next = String(!on);
  node.append(button);
  return button;
}

// A probe is tri-state on purpose: an unscheduled opponent is not a fault, and
// painting it red on every idle afternoon teaches the operator to ignore red.
function probeRow(probe) {
  const state = probe.reachable === true ? 'ok'
    : probe.reachable === false ? 'bad' : 'idle';
  const url = probe.url || OFF;
  return `<div class="row probe ${state}">
      <span>${probe.name}</span>
      <code>${url}</code>
      <strong>${probe.detail}</strong>
    </div>`;
}

export function renderLiveness(node, liveness) {
  const probes = (liveness && liveness.probes) || [];
  if (!probes.length) {
    node.innerHTML = '<div class="row"><span>No endpoints to probe yet</span></div>';
    return;
  }
  const blocking = (liveness.blocking || []);
  const summary = blocking.length
    ? `<div class="alert">Would block a match: ${blocking.join(', ')}</div>`
    : '<div class="mini">Everything configured is answering.</div>';
  node.innerHTML = summary + probes.map(probeRow).join('');
}

const getJson = (path) => fetch(path).then((r) => r.json());

export function wireTesting() {
  const practiceNode = document.getElementById('practice');
  const livenessNode = document.getElementById('liveness');
  const probeButton = document.getElementById('probe');
  if (!practiceNode) return;

  async function paintPractice() {
    const state = await getJson('/api/control');
    const button = renderPractice(practiceNode, state.practice, state.peer.controls_enabled);
    button.addEventListener('click', async () => {
      button.disabled = true;
      // Re-read rather than trusting the response we just got: the point of
      // the switch is that the page and the send path agree about the mode.
      try {
        await fetch('/api/control/practice', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: button.dataset.next === 'true' }),
        });
      } finally {
        paintPractice();
      }
    });
  }

  async function probe() {
    probeButton.disabled = true;
    probeButton.textContent = 'probing…';
    try {
      renderLiveness(livenessNode, await getJson('/api/liveness'));
    } finally {
      probeButton.disabled = false;
      probeButton.textContent = 'Probe endpoints';
    }
  }

  // On demand, not on a timer: probing opens real sockets, and a panel that
  // dialled the opponent every few seconds would be a background process
  // nobody asked for.
  probeButton.addEventListener('click', probe);
  paintPractice();
  probe();
}
