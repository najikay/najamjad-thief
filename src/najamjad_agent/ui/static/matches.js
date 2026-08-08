// Match browser and match-day cockpit.
//
// Both read from files we already filed, so the page cannot claim a result the
// artifacts do not contain. Fetched rather than pushed: neither changes during
// a turn, and putting them on the socket would add traffic to the one path that
// has to stay quick.

const text = (value) => (value === null || value === undefined ? "—" : String(value));

function scoreLine(scores) {
  return Object.entries(scores || {})
    .map(([group, points]) => `${group} ${points}`)
    .join(" · ") || "—";
}

// A game nobody audited is not a game that failed its audit. The two get
// different words and different colours, because collapsing them would turn a
// timeout into an accusation of forgery.
function auditTag(match) {
  if (match.tampered > 0) return `<span class="tag bad">TAMPERED ×${match.tampered}</span>`;
  if (match.verified === match.num_sub_games && match.num_sub_games > 0) {
    return `<span class="tag ok">all verified</span>`;
  }
  return `<span class="tag warn">${match.verified}/${match.num_sub_games} verified</span>`;
}

export function renderStandings(node, table) {
  if (!node) return;
  if (!table || !table.matches) {
    node.innerHTML = `<p class="hint">No matches filed yet.</p>`;
    return;
  }
  const warnings = [];
  if (table.unreported && table.unreported.length) {
    warnings.push(`<span class="tag bad">unreported: ${table.unreported.join(", ")}</span>`);
  }
  if (table.tampered && table.tampered.length) {
    warnings.push(`<span class="tag bad">tampered: ${table.tampered.join(", ")}</span>`);
  }
  node.innerHTML = `
    <div class="row">
      <!-- "counted" here was a lie: `standings()` counts every result
           artifact on disk, practice and warm-ups included. The number we
           *declare* under rules 37-38 comes from the counted-match ledger
           and is a different figure entirely. An operator who reads this
           panel and repeats it is how a team declares a false count. -->
      <span class="tag">${table.matches} series filed</span>
      <span class="tag">${table.distinct_opponents} distinct opponents</span>
      <span class="tag">${table.won} won</span>
      <span class="tag">${table.points} points</span>
      ${warnings.join(" ")}
    </div>`;
}

export function renderMatches(node, matches) {
  if (!node) return;
  if (!matches || !matches.length) {
    node.innerHTML = `<p class="hint">Nothing filed yet. A played match writes four artifacts.</p>`;
    return;
  }
  node.innerHTML = matches
    .map(
      (match) => `
      <div class="match">
        <div class="row">
          <strong>${text(match.game_id)}</strong>
          ${auditTag(match)}
          <span class="tag">${scoreLine(match.total_score)}</span>
          <span class="tag ${match.winner_group ? "ok" : ""}">${
            match.series_tie ? "tie" : "winner: " + text(match.winner_group)
          }</span>
          ${match.reported ? "" : '<span class="tag bad">not reported</span>'}
        </div>
        <div class="mini">${match.sub_games
          .map(
            (game) =>
              `g${String(game.sub_game_number).padStart(2, "0")} ${text(game.result)}` +
              ` (${scoreLine(game.score)})`
          )
          .join(" · ")}</div>
        <div class="mini hint">${match.artifacts.length} artifacts — ${text(match.path)}</div>
      </div>`
    )
    .join("");
}

export function renderCockpit(node, cockpit) {
  if (!node) return;
  if (!cockpit) {
    node.innerHTML = `<p class="hint">Readiness unavailable.</p>`;
    return;
  }
  const checks = (cockpit.checks || [])
    .map(
      (check) =>
        `<div class="row"><span class="tag ${check.passed ? "ok" : "bad"}">${
          check.passed ? "ok" : "FAIL"
        }</span> ${text(check.name)} <span class="hint">${text(check.detail)}</span></div>`
    )
    .join("");
  node.innerHTML = `
    <div class="row">
      <span class="tag ${cockpit.exit_code === 0 ? "ok" : "warn"}">${
        cockpit.exit_code === 0 ? "MATCH READY" : "not ready"
      }</span>
      <span class="tag">${text(cockpit.public_url)}</span>
    </div>
    ${checks || '<p class="hint">No checks configured — set network.opponent_url.</p>'}`;
}

export async function refreshMatches() {
  try {
    const [matches, cockpit] = await Promise.all([
      fetch("/api/matches").then((response) => response.json()),
      fetch("/api/cockpit").then((response) => response.json()),
    ]);
    renderStandings(document.getElementById("standings"), matches.standings);
    renderMatches(document.getElementById("matches"), matches.matches);
    renderCockpit(document.getElementById("cockpit"), cockpit);
  } catch {
    // A dashboard that cannot reach its own API must not take the page down;
    // the live panels are driven by the socket and keep working.
  }
}
