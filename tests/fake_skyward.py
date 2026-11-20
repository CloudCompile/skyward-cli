"""A tiny fake Skyward, reproducing the real portal's protocol.

Matches what the real portal does (Nov 2026):

  GET  /Sky/web/seplog01.w   login form (detailform) with hidden state
  POST /Sky/web/skyporthttp.w  the login form itself posts here
                               (requestAction=eel&codeType=tryLogin&...)
                               -> "<li>dwd^webrecid^wfaaclrecid^wfaacl^nameid^
                               duserid^2^sfhome01.w^false^no ^no^no^^enc^encses^..</li>"
  POST /Sky/web/<page>.w     any page, with those tokens as form fields and pg=<page>
  POST /Sky/web/httploader.p?file=<page>   AJAX calls; requires sessionid

The rendered school data lives in fixtures/pages.py so tests can assert on it.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from fixtures import pages

USER = "1234567"
PASSWORD = "correct horse"
TOKENS = ["1001", "2000001", "30000001", "40000001", "111111", USER, "2", "sfhome01.w",
          "false", "no ", "no", "no", "", "EnCaBcDxYzWqRsTu", "SeSsIoNkEyAbCdEf"]


class FakeSkyward:
    def __init__(self):
        self.requests: list[tuple[str, str, dict[str, list[str]]]] = []
        self.logged_in = False
        self.pages_served: list[str] = []

    # ── routing ──────────────────────────────────────────────────────────

    def handle(self, method: str, path: str, form: dict[str, list[str]]) -> tuple[int, str]:
        self.requests.append((method, path, form))
        page = urlsplit(path).path.rsplit("/", 1)[-1]
        qs = parse_qs(urlsplit(path).query)
        if method == "GET" and page == "seplog01.w":
            return 200, pages.login_page()
        if method == "POST" and page == "skyporthttp.w":
            user = form.get("login", [""])[0]
            pw = form.get("password", [""])[0]
            if page == "skyporthttp.w" and "hAnon" not in form:
                return 200, "<li>Invalid login or password.</li>"
            if user != USER or pw != PASSWORD:
                return 200, "<li>Invalid login or password.</li>"
            if form.get("securityCode", [""])[0] == "MFA":
                return 200, "<li>Please enter the security code.</li>"
            self.logged_in = True
            return 200, "<li>%s</li>" % "^".join(TOKENS)
        if not self.logged_in or form.get("nameid", [""])[0] != "111111":
            return 200, pages.login_page()
        if page == "httploader.p":
            target = qs.get("file", [""])[0]
            if "sessionid" not in form:
                return 200, pages.ajax_error("Session is invalid")
            action = form.get("action", [""])[0]
            if target == "sfgradebook002.w" and action == "viewGPARank":
                self.pages_served.append("gpa")
                return 200, pages.gpa_dialog()
            return 200, pages.ajax_error("Unknown request")
        table = {
            "sfgradebook001.w": pages.gradebook,
            "sfschedule001.w": pages.schedule,
            "sfattendance001.w": pages.attendance,
            "sfhome01.w": pages.home,
        }
        if page in table:
            self.pages_served.append(page)
            return 200, table[page]()
        return 404, "<html><body>not found</body></html>"

    def __enter__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code: int, body: str):
                data = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=UTF-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                code, body = fake.handle("GET", self.path, {})
                self._reply(code, body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else ""
                form = parse_qs(raw, keep_blank_values=True)
                code, body = fake.handle("POST", self.path, form)
                self._reply(code, body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()

    @property
    def base(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/Sky/web/"
