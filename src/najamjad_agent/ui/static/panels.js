// Panel renderers. Each takes the view model the SDK produced and paints it.
// No panel computes anything about the game — that all happened server-side.

export function renderTurn(node, turn) {
  if (!turn || !turn.available) {
    node.textContent = 'NO GAME';
    node.className = 'banner';
    return;
  }
  const yours = !turn.locked;
  node.textContent = yours ? `YOUR TURN — ${turn.phase}` : `LOCKED — ${turn.phase}`;
  node.className = yours ? 'banner active' : 'banner';
  node.title = `step ${turn.step} · recent: ${(turn.recent_phases || []).join(' → ')}`;
}

export function renderTranscript(node, messages) {
  node.replaceChildren(...(messages || []).map((message) => {
    const wrap = document.createElement('div');
    wrap.className = `msg ${message.direction === 'out' ? 'out' : 'in'}`;
    const meta = document.createElement('div');
    meta.className = 'meta';
    const who = message.direction === 'out' ? 'us' : 'them';
    const model = message.model || message.provider || 'peer';
    meta.textContent = `step ${message.step} · ${who} · ${model}`;
    const body = document.createElement('div');
    body.textContent = message.text;
    wrap.append(meta, body);
    return wrap;
  }));
}

export function renderNegotiation(node, steps) {
  if (!steps || steps.length === 0) {
    node.innerHTML = '<p class="mini">No negotiation yet.</p>';
    return;
  }
  node.replaceChildren(...steps.map((step) => {
    const row = document.createElement('div');
    row.className = 'msg';
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = `${step.action || 'step'} · ${step.stage || ''}`;
    const body = document.createElement('div');
    body.textContent = describeStep(step);
    row.append(meta, body);
    return row;
  }));
}

// The timeline carries whatever each step needed to record, so the renderer
// summarises the fields that are actually present rather than assuming a shape.
function describeStep(step) {
  const skip = new Set(['action', 'stage']);
  const parts = Object.entries(step)
    .filter(([key]) => !skip.has(key))
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? flatten(value) : value}`);
  return parts.length ? parts.join(' · ') : '—';
}

function flatten(value) {
  if (Array.isArray(value)) return value.join(', ');
  return Object.entries(value || {}).map(([k, v]) => `${k}=${v}`).join(', ') || '—';
}

export function renderBudget(node, budget) {
  if (!budget || !budget.available) {
    node.innerHTML = '<p class="mini">Token meter idle.</p>';
    return;
  }
  const percent = Math.min(100, Math.round((budget.ratio || 0) * 100));
  const level = budget.degraded ? 'bad' : budget.warning ? 'warn' : '';
  node.innerHTML = `
    <div class="row"><span>Series</span>
      <strong>${budget.series_spent.toLocaleString()} / ${budget.series_limit.toLocaleString()}</strong></div>
    <div class="bar ${level}"><span style="width:${percent}%"></span></div>
    <div class="mini">${percent}% used${budget.degraded ? ' · degraded to templates' : ''}</div>`;
}

export function renderGatekeepers(node, services) {
  node.replaceChildren(...(services || []).map((service) => {
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `<span>${service.service}</span>
      <span>${service.in_flight} in flight · ${service.waiting} queued · ${service.calls_made} calls</span>`;
    return row;
  }));
}

export function renderProvider(node, provider) {
  const active = provider && provider.available && provider.active;
  node.textContent = `provider: ${active || '—'}`;
  // Green only when a router is actually answering. A badge that is green
  // whatever happens is decoration, not status.
  node.className = active ? 'tag ok' : 'tag';
}

// A6's report simply never went out when we were not the initiating side, and
// nothing on screen said so. This panel is that missing signal.
export function renderReport(node, report) {
  if (!report) return;
  const agreement = report.agreement === null ? 'undecided' : String(report.agreement);
  const delivery = report.sent
    ? `sent · ${report.message_id}`
    : report.error || (report.reconciled ? 'NOT SENT' : 'waiting for the match to end');
  node.className = report.needs_attention ? 'alert' : '';
  node.innerHTML = `
    <div class="row"><span>Reconciled</span><strong>${report.status}</strong></div>
    <div class="row"><span>Mutual agreement</span><strong>${agreement}</strong></div>
    <div class="row"><span>Email</span><strong>${delivery}</strong></div>`;
  if (report.differences && report.differences.length) {
    const list = document.createElement('div');
    list.className = 'mini';
    list.textContent = `Differences: ${report.differences.join('; ')}`;
    node.append(list);
  }
}

export function appendEvent(node, event, limit = 200) {
  const row = document.createElement('div');
  const name = event.event || event.type || 'event';
  row.textContent = `${event.ts || ''} ${name} ${summarise(event)}`;
  node.prepend(row);
  while (node.childElementCount > limit) node.lastElementChild.remove();
}

function summarise(event) {
  const skip = new Set(['type', 'event', 'ts', 'game_uid']);
  return Object.entries(event)
    .filter(([key]) => !skip.has(key))
    .map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(' ');
}
