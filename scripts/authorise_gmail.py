"""One-time Gmail consent, run by a human, never by the agent.

Two rules shape this script:

* **Send-only scope.** Book rule 30 requires least privilege. The Assignment 6
  token carried `gmail.modify`, which grants read *and* write over the whole
  mailbox — far more than a report sender needs, and visibly wrong to a grader
  checking the rule.
* **Never mid-match.** This is the only place an interactive browser flow may
  happen. Assignment 6 lost matches because consent could be demanded from a
  background thread with nobody watching; the agent itself now refuses to open
  a browser and fails loudly pointing here instead.

WSL has no browser, so nothing is launched automatically: the URL is printed for
you to open on Windows. A fixed callback port keeps the redirect predictable,
and `--manual` covers the case where Windows cannot reach the WSL listener at
all.

Usage:

    uv run python scripts/authorise_gmail.py            # print URL, wait for redirect
    uv run python scripts/authorise_gmail.py --manual   # paste the redirect URL back
    uv run python scripts/authorise_gmail.py --check    # inspect, no browser
"""

import argparse
import json
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SECRETS = Path(__file__).resolve().parent.parent / "secrets"
CLIENT_FILE = SECRETS / "credentials.json"
TOKEN_FILE = SECRETS / "token.json"
CALLBACK_PORT = 8765


def inspect(path: Path) -> int:
    """Report what a stored token grants, and whether it still works.

    This printed `refreshable: True` for a token Google had already revoked,
    because it read whether a `refresh_token` *field was present* rather than
    trying to use it. The RUNBOOK tells an operator to run this the evening
    before a match, so a dead token passed its own check and the failure
    surfaced only when a report did not send — which rules 33-35 score as not
    having played at all.

    The refresh is now attempted through `load_credentials`, the same function
    the agent itself uses, so this check and the real send path cannot disagree
    again by construction.
    """
    if not path.exists():
        print(f"no token at {path} — run this script without --check to create one")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    scopes = data.get("scopes", [])
    print(f"token      : {path}")
    print(f"scopes     : {scopes}")
    if scopes != SCOPES:
        print(f"WRONG SCOPE: need exactly {SCOPES}")
        print("Re-run without --check to consent again with send-only access.")
        return 1
    print("scope is correct (send-only, book rule 30)")

    sys.path.insert(0, str(SECRETS.parent / "src"))
    try:
        from najamjad_agent.reporting.gmail_auth import load_credentials

        credentials = load_credentials(path)
    except Exception as error:  # noqa: BLE001 - the reason is the whole output
        print(f"\nREFRESH FAILED: {type(error).__name__}: {error}")
        print("The token is present but unusable — a match would write its artifacts")
        print("and fail to deliver the report. Re-run this script without --check.")
        return 1
    print(f"refresh    : OK (valid={getattr(credentials, 'valid', True)})")
    print("this token can actually send")
    return 0


def _flow():
    """Build the installed-app flow, or explain what is missing."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_FILE.exists():
        raise FileNotFoundError(
            f"missing OAuth client at {CLIENT_FILE}; download the Desktop client "
            "JSON from Google Cloud Console and put it there"
        )
    return InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)


def _store(credentials) -> int:
    """Persist the token and say where it went."""
    SECRETS.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    print(f"\ntoken written to {TOKEN_FILE} with scopes {SCOPES}")
    print("This file is git-ignored and must never be committed (book rules 39-40).")
    return 0


def authorise() -> int:
    """Consent with a local callback listener on a fixed, predictable port.

    The URL is *not* printed here: `redirect_uri` is only set once the listener
    starts, so a URL built beforehand is missing that parameter and Google
    rejects it with "Missing required parameter: redirect_uri". The library
    prints the correct URL itself — that is the one to open.
    """
    flow = _flow()
    print("A URL will be printed below. Open it in your Windows browser and approve.")
    print(f"The redirect lands on http://localhost:{CALLBACK_PORT}, which WSL forwards.")
    print("(If the browser cannot reach that address, press Ctrl+C and re-run with --manual)\n")
    credentials = flow.run_local_server(
        port=CALLBACK_PORT, open_browser=False, timeout_seconds=300
    )
    return _store(credentials)


def authorise_manually() -> int:
    """Consent without any callback listener — paste the redirect URL back."""
    flow = _flow()
    flow.redirect_uri = f"http://localhost:{CALLBACK_PORT}"
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print("Open this URL in your Windows browser and approve:\n")
    print(url)
    print(
        "\nThe browser will land on a 'cannot connect' page — that is expected.\n"
        "Copy the FULL address bar contents (it contains ?code=...) and paste it here."
    )
    response = input("\nRedirect URL: ").strip()
    if not response:
        print("nothing pasted; aborted")
        return 1
    flow.fetch_token(authorization_response=response)
    return _store(flow.credentials)


def main() -> int:
    """Entry point: consent (auto or manual), or inspect an existing token."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="inspect the token, no browser")
    parser.add_argument("--manual", action="store_true", help="paste the redirect URL back")
    arguments = parser.parse_args()
    if arguments.check:
        return inspect(TOKEN_FILE)
    try:
        return authorise_manually() if arguments.manual else authorise()
    except FileNotFoundError as error:
        print(error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
