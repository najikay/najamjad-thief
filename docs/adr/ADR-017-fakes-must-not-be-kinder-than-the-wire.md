# ADR-017 — A fake must not be kinder than the thing it stands in for

**Status:** accepted (build-time, E21)

**Context:** Three separate defects survived a green suite of 1,500+ tests
because our test doubles were more forgiving than reality:

- the fake transport wrapped the audit payload in an envelope the real one never
  added, so the domain sent a bare list that every real peer rejected;
- the in-memory link returned `None` immediately on an empty queue instead of
  blocking, so the first peer to look forfeited a game nobody was losing;
- both peers shared our own conventions, so no test could see an interop bug.

**Decision:** a fake reproduces the *contract* of what it replaces, including
its framing, its blocking behaviour and its refusals. Where a fake must differ,
the difference is documented in the fake itself and justified.

**Consequence:** the blocking link now blocks with a timeout, matching
`PeerTransport`; the fake audit channel forwards untouched; and interop is
verified against a foreign implementation rather than against ourselves.

**The general rule this encodes:** a green suite proves the code agrees with our
assumptions, not that the assumptions are right.
