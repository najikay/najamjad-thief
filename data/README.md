# data/

Input data, kept apart from everything the project *produces*.

The guidelines mandate this directory (§2.4). It is deliberately small here,
because this project's inputs are not datasets: the game is generated, the
opponent is a live peer, and the only fixed inputs are the agreed terms
(`config/game.json`) and the reference fixtures we test against.

| What | Where | Why not here |
|---|---|---|
| Agreed game terms | `config/game.json` | Signed configuration, not data |
| Reference artifacts | `tests/goldens/` | Test fixtures — they belong beside the tests that assert on them |
| Sweep and baseline results | `results/` | **Output**, not input |
| Match artifacts | `workspace/artifacts/`, `matches/` | Output, per match |

`map_areas.json` is the one genuine input: the landmark vocabulary the template
provider draws on for hints, keyed by the agreed `world.map_area`.
