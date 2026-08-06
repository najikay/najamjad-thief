"""The opponent's tool names and argument names — protocol facts, not our choices.

Split out of `mcp_client` because none of it is client behaviour: it is a
transcription of the reference implementation's public surface, which every team
builds on, and it changes only when the reference does.

The argument names are the part worth reading twice. The reference declares
`message` on three tools and `payload` on `submit_audit`, and its client sends
exactly that. We sent `payload` everywhere, so a reference-derived opponent —
which is most of the class — rejected every turn and every proposal we sent, in
both directions, and the failure looked like a network problem rather than a
spelling one. Verified against the real simulator before and after the fix.
"""

from __future__ import annotations

#: Our internal message kind -> the tool name the opponent exposes.
TOOL_FOR_KIND = {
    "negotiate": "negotiate",
    "turn": "receive_turn",
    "audit": "submit_audit",
    "control": "receive_control",
}

#: Tool name -> the keyword the reference declares for its body.
ARGUMENT_FOR_TOOL = {
    "negotiate": "message",
    "receive_turn": "message",
    "receive_control": "message",
    "submit_audit": "payload",
}
