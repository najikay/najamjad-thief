// Replay viewer client.
//
// It renders a verdict it did not compute: no hashing happens here. Two
// implementations of the same SHA-256 is how a viewer ends up disagreeing with
// the audit that already ran (T-1910).

const el = (id) => document.getElementById(id);
let steps = [];
let cursor = 0;

async function boot() {
  const [summary, body] = await Promise.all([
    fetch('/api/replay/summary').then((r) => r.json()),
    fetch('/api/replay/steps').then((r) => r.json()),
  ]);
  steps = body.steps || [];
  renderSummary(summary);
  renderStrip();
  // ?step=N deep-links a specific step — how the screenshot pass and a bug
  // report both point at one record rather than describing how to get there.
  show(Number(new URLSearchParams(location.search).get('step')) || 0);
}

function renderSummary(summary) {
  const banner = el('banner');
  if (!summary.loaded) {
    banner.textContent = 'NO LOG LOADED';
    banner.className = 'verdict pending';
    showErrors([summary.error].filter(Boolean));
    return;
  }
  banner.textContent = summary.banner;
  banner.className = `verdict ${summary.passed ? 'ok' : 'bad'}`;
  el('game').textContent = summary.game_id || 'unknown game';
  el('counts').textContent = `${summary.verified}/${summary.steps} steps verified`;
  showErrors(summary.errors || []);
  if (summary.void) banner.textContent += ' — GAME VOID (rule 19)';
}

function showErrors(messages) {
  const node = el('errors');
  node.hidden = messages.length === 0;
  node.textContent = messages.join(' · ');
}

function renderStrip() {
  const strip = el('strip');
  strip.replaceChildren(...steps.map((step, index) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = `chip ${step.verified ? '' : 'bad'}`;
    chip.textContent = step.step;
    // Record index as well as step number: a log may carry two records with
    // the same step (the reference sample does), and identical chips are
    // unclickable-looking noise without something to tell them apart.
    chip.title = `record ${index} · step ${step.step} · ${step.verified ? 'verified' : step.reason}`;
    chip.addEventListener('click', () => show(index));
    return chip;
  }));
  el('slider').max = String(Math.max(0, steps.length - 1));
  el('steptotal').textContent = String(steps.length);
}

function renderBoard(step) {
  const node = el('board');
  if (!step.size) {
    node.replaceChildren(Object.assign(document.createElement('p'), {
      className: 'legend', textContent: 'This record carries no board (step-zero declaration).',
    }));
    return;
  }
  const own = (step.position || []).join(',');
  const barriers = new Set((step.barriers || []).map((cell) => cell.join(',')));
  const cells = [];
  for (let row = 0; row < step.size; row += 1) {
    for (let col = 0; col < step.size; col += 1) {
      const key = `${row},${col}`;
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.title = `(${key})`;
      if (barriers.has(key)) cell.classList.add('barrier');
      if (key === own) { cell.classList.add('self'); cell.textContent = 'X'; }
      cells.push(cell);
    }
  }
  node.style.gridTemplateColumns = `repeat(${step.size}, 1fr)`;
  node.replaceChildren(...cells);
}

function renderRecord(step) {
  const rows = [
    ['Kind', step.kind], ['Move', step.move || '—'], ['Intent', step.intent || '—'],
    ['Hint', step.hint || '—'], ['Model', step.model || '—'], ['Tokens', step.tokens],
  ];
  if (step.warning) rows.push(['Warning', step.warning]);
  el('record').replaceChildren(...rows.map(([label, value]) => {
    const row = document.createElement('div');
    row.className = 'row';
    row.append(
      Object.assign(document.createElement('span'), { textContent: label }),
      Object.assign(document.createElement('span'), { textContent: String(value) }),
    );
    return row;
  }));
  const state = step.verified ? 'match' : 'differ';
  el('hashes').innerHTML = `
    <div class="row">stored:&nbsp; ${step.commit}</div>
    <div class="row ${state}">recomputed: ${step.recomputed || '(unavailable)'}</div>
    <div class="row ${state}">${step.verified ? 'identical — this step is genuine' : step.reason}</div>`;
}

function show(index) {
  if (!steps.length) return;
  cursor = Math.max(0, Math.min(steps.length - 1, index));
  const step = steps[cursor];
  el('stepno').textContent = String(step.step);
  el('slider').value = String(cursor);
  renderBoard(step);
  renderRecord(step);
  [...el('strip').children].forEach((chip, position) => {
    chip.classList.toggle('current', position === cursor);
  });
  el('first').disabled = el('prev').disabled = cursor === 0;
  el('last').disabled = el('next').disabled = cursor === steps.length - 1;
}

el('first').addEventListener('click', () => show(0));
el('prev').addEventListener('click', () => show(cursor - 1));
el('next').addEventListener('click', () => show(cursor + 1));
el('last').addEventListener('click', () => show(steps.length - 1));
el('slider').addEventListener('input', (event) => show(Number(event.target.value)));
document.addEventListener('keydown', (event) => {
  if (event.key === 'ArrowLeft') show(cursor - 1);
  if (event.key === 'ArrowRight') show(cursor + 1);
});

boot();
