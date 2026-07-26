// The client: one WebSocket, no polling.
//
// Assignment 6 polled REST endpoints on a timer and still missed updates. The
// only timer here is the reconnect backoff, and a dropped socket says so on
// screen instead of silently showing stale numbers (T-1824).

import { renderBoard } from './board.js';
import {
  appendEvent, renderBudget, renderGatekeepers, renderNegotiation,
  renderProvider, renderReport, renderTranscript, renderTurn,
} from './panels.js';

const el = (id) => document.getElementById(id);
const MAX_BACKOFF = 10000;
let backoff = 500;

function paint(snapshot) {
  renderBoard(el('board'), snapshot.board);
  renderTurn(el('banner'), snapshot.turn);
  renderTranscript(el('transcript'), snapshot.transcript);
  renderNegotiation(el('negotiation'), snapshot.negotiation);
  renderBudget(el('budget'), snapshot.budget);
  renderGatekeepers(el('gatekeepers'), snapshot.gatekeepers);
  renderReport(el('report'), snapshot.report);
  renderProvider(el('provider'), snapshot.provider);
  if (snapshot.board && snapshot.board.role) el('role').textContent = snapshot.board.role;
}

function setConnection(state, text) {
  const badge = el('conn');
  badge.className = `tag ${state}`;
  badge.textContent = text;
  document.querySelectorAll('.panel').forEach((panel) => {
    panel.classList.toggle('stale', state === 'bad');
  });
}

// At most one snapshot request is ever in flight. Without this, a burst of
// events becomes a burst of HTTP round-trips — which is the polling this page
// exists to avoid, just triggered by the socket instead of a timer. Events
// arriving mid-request set `dirty`, so the final state is always fetched once
// the current request lands; no update is dropped and none is duplicated.
let syncing = false;
let dirty = false;

async function resync() {
  if (syncing) {
    dirty = true;
    return;
  }
  syncing = true;
  try {
    const response = await fetch('/api/snapshot');
    paint(await response.json());
  } catch (error) {
    console.warn('snapshot failed', error);
  } finally {
    syncing = false;
    if (dirty) {
      dirty = false;
      resync();
    }
  }
}

// A page opened mid-match would otherwise show an empty feed until the next
// event happened to fire — the socket only carries what arrives after we join.
async function backfillEvents() {
  try {
    const { events } = await fetch('/api/events').then((r) => r.json());
    events.forEach((event) => appendEvent(el('events'), event));
  } catch (error) {
    console.warn('event backfill failed', error);
  }
}

function handle(frame) {
  if (frame.type === 'snapshot') {
    paint(frame);
    return;
  }
  appendEvent(el('events'), frame);
  // Any state-changing event invalidates the panels, so pull one fresh
  // snapshot rather than reimplementing the domain's transitions in JS.
  resync();
}

function connect() {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
  const socket = new WebSocket(url);

  socket.onopen = () => {
    backoff = 500;
    setConnection('ok', 'live');
  };
  socket.onmessage = (message) => handle(JSON.parse(message.data));
  socket.onclose = () => {
    setConnection('bad', `reconnecting in ${Math.round(backoff / 1000)}s…`);
    setTimeout(connect, backoff);
    backoff = Math.min(MAX_BACKOFF, backoff * 2);
  };
  socket.onerror = () => socket.close();
}

// Backfill completes before the socket opens. Both paths prepend, so a history
// fetch that landed after a live event would stack older entries on top of
// newer ones — a feed that reads correctly but is silently out of order.
async function boot() {
  setConnection('warn', 'connecting…');
  await Promise.allSettled([resync(), backfillEvents()]);
  connect();
}

boot();
