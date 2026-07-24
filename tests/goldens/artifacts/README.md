# Golden lifecycle artifacts (provenance)

The four sample game-lifecycle JSON files (`declaration_`, `config__g01`, `log__g01`,
`result_`) were copied verbatim from the course reference simulator:

- **Source repo:** https://github.com/rmisegal/Game-P2P-Cop-Chase
- **Path:** `docs/sample-run/`
- **Source commit:** `960499fd5e8777b4929625f5d8fdcf2ab4677b54`
- **Copied:** 2026-07-24

Why they exist here (PLAN ADR-012, PRD A1): the project book names these files but does not
reproduce their schemas; the reference artifacts are therefore the authoritative shape our
pydantic schemas (E09) must parse, and our own emitted artifacts must round-trip to the same
structure. Do not edit these files — refresh only by re-copying from a newer source commit
and updating this provenance note.
