"""One-shot Spotify OAuth bootstrap. Run on the Mac, not the LXC.

Prompts for client_id + client_secret, opens a browser for user consent,
catches the redirect on 127.0.0.1:8765/callback, swaps the auth code for
a refresh token, and prints it. Paste the refresh token into
/etc/wizmood/config.toml on the LXC. The LXC never does this flow itself.

Requires Python 3.11+. No third-party dependencies.
"""

import base64
import getpass
import http.server
import secrets
import socketserver
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

REDIRECT_URI = "http://127.0.0.1:8765/callback"
SCOPES = "user-read-currently-playing user-read-playback-state"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


class _Handler(http.server.BaseHTTPRequestHandler):
    captured: dict[str, str] = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = dict(urllib.parse.parse_qsl(parsed.query))
        _Handler.captured.update(params)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>Done.</h1><p>You can close this tab.</p>")

    def log_message(self, format, *args):
        pass


def wait_for_code(state: str) -> str:
    with socketserver.TCPServer(("127.0.0.1", 8765), _Handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        while "code" not in _Handler.captured and "error" not in _Handler.captured:
            threading.Event().wait(0.2)
        httpd.shutdown()

    if _Handler.captured.get("state") != state:
        sys.exit("state mismatch; possible CSRF")
    if "error" in _Handler.captured:
        sys.exit(f"Spotify returned error: {_Handler.captured['error']}")
    return _Handler.captured["code"]


def exchange(client_id: str, client_secret: str, code: str) -> dict:
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as resp:
        import json
        return json.load(resp)


def main() -> None:
    client_id = input("Spotify client_id: ").strip()
    client_secret = getpass.getpass("Spotify client_secret (hidden): ").strip()
    if not client_id or not client_secret:
        sys.exit("both client_id and client_secret are required")

    state = secrets.token_urlsafe(16)
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    })
    url = f"{AUTH_URL}?{params}"
    print(f"\nOpening browser. If it doesn't open, paste this URL manually:\n  {url}\n")
    webbrowser.open(url)

    code = wait_for_code(state)
    tokens = exchange(client_id, client_secret, code)

    refresh = tokens.get("refresh_token")
    if not refresh:
        sys.exit(f"no refresh_token in response: {tokens}")

    print("\nSuccess. Paste this into /etc/wizmood/config.toml under [spotify]:\n")
    print(f'  client_id = "{client_id}"')
    print(f'  client_secret = "{client_secret}"')
    print(f'  refresh_token = "{refresh}"')
    print("\nDo not commit any of these to git.")


if __name__ == "__main__":
    main()
