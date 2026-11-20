"""Skyward client built on the real Family/Student Access protocol.

Flow (confirmed against a live district portal, Nov 2026):

1. GET  web/seplog01.w           -> login form + hidden anti-anon fields (hAnon)
2. POST web/skyporthttp.w        -> the login form itself posts here with
   requestAction=eel&codeType=tryLogin&codeValue=login. Response is a
   caret-delimited token list inside <li>: dwd^webrecid^wfaaclrecid^wfaacl^
   nameid^duserid^usertype^homepage^...^enc^encses^...
3. POST web/sfgradebook001.w etc. with those tokens as form fields (plus
   pg=<page>) -> normal HTML pages.

Sessions are short lived and a second login can evict the first, so we log
in once per run and never keep cookies on disk.
"""

from __future__ import annotations

import getpass
import html as _html
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import requests

from . import parse

# A placeholder, not a real district: which Skyward instance to talk to is a
# per-user setting. Pass --base, set SKYWARD_BASE, or put `base=` in the config.
DEFAULT_BASE = "https://skyward.example.org/Sky/web/"
LOGIN_PAGE = "seplog01.w"
LOGIN_POST = "skyporthttp.w"
GRADEBOOK = "sfgradebook001.w"
GRADEBOOK_DIALOG = "sfgradebook002.w"
SCHEDULE = "sfschedule001.w"
ATTENDANCE = "sfattendance001.w"
HOME = "sfhome01.w"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# Token order in the skyporthttp.w reply (positional, per Progress's
# extrainfo protocol). Only the ones we use are named.
TOKEN_NAMES = [
    "dwd", "webrecid", "wfaaclrecid", "wfaacl", "nameid", "duserid", "usertype",
    "homepage", "fromHomePage", "hasMessaging", "x1", "x2", "x3", "enc", "encses",
    "loginHistoryId",
]


class SkywardError(Exception):
    """Anything the portal rejects or we cannot parse."""


class LoginError(SkywardError):
    """Bad username/password, or the account needs a security code (MFA)."""


class SessionExpired(SkywardError):
    """The portal answered a page request with the login page."""


@dataclass
class Credentials:
    username: str
    password: str
    security_code: str = ""


# ── form scraping ────────────────────────────────────────────────────────

_FORM_RE = re.compile(r"<form\b[^>]*>.*?</form>", re.S | re.I)
_INPUT_RE = re.compile(r"<input\b([^>]*)>", re.S | re.I)
_ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.S)


def form_fields(page_html: str) -> dict[str, str]:
    """All hidden inputs across all forms (login page, nav form, grid form)."""
    out: dict[str, str] = {}
    for form in _FORM_RE.finditer(page_html):
        for tag in _INPUT_RE.finditer(form.group(0)):
            a = _attrs(tag.group(1))
            name = a.get("name") or a.get("id")
            if not name:
                continue
            kind = a.get("type", "text").lower()
            if kind in ("checkbox", "radio") and "checked" not in a:
                continue
            out[name] = _html.unescape(a.get("value", ""))
    return out


def _attrs(tag: str) -> dict[str, str]:
    return {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3))
            for m in _ATTR_RE.finditer(tag)}


def inline_state(page_html: str) -> dict[str, str]:
    """sff.sv('key', 'value') state variables, which carry the real session ids."""
    out = {}
    for m in re.finditer(r"sff\.sv\('([^']+)',\s*'([^']*)'\)", page_html):
        out[m.group(1)] = m.group(2)
    return out


# ── client ───────────────────────────────────────────────────────────────

@dataclass
class Session:
    tokens: dict[str, str]
    state: dict[str, str] = field(default_factory=dict)
    user_agent: str = USER_AGENT

    def payload(self, page: str, extra: dict[str, Any] | None = None,
                ajax: bool = False) -> dict[str, str]:
        data = {k: str(v) for k, v in self.tokens.items()}
        state = dict(self.state)
        if not ajax:
            # sessionid is an AJAX-only parameter; the page forms reject it.
            state.pop("sessionid", None)
        data.update({k: str(v) for k, v in state.items() if isinstance(v, str) and len(v) < 64})
        data["pg"] = page
        for k, v in (extra or {}).items():
            data[k] = "" if v is None else str(v)
        return data


class SkywardClient:
    def __init__(self, base: str = DEFAULT_BASE, timeout: float = 30.0,
                 http: requests.Session | None = None):
        self.base = base if base.endswith("/") else base + "/"
        parts = urlsplit(self.base)
        self.root = f"{parts.scheme}://{parts.netloc}/"
        self.timeout = timeout
        self.http = http or requests.Session()
        self.http.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.session: Session | None = None
        self._cache: dict[str, str] = {}

    def _url(self, page: str) -> str:
        if "://" in page:
            return page
        if page.startswith("/"):
            return self.root.rstrip("/") + page
        return self.base + page.rsplit("/", 1)[-1]

    # ── login ────────────────────────────────────────────────────────────

    def login(self, creds: Credentials) -> Session:
        page = self.http.get(self._url(LOGIN_PAGE), timeout=self.timeout)
        page.raise_for_status()
        if not _is_login_page(page.text):
            raise LoginError("could not find the Skyward login form; wrong --base?")

        data = form_fields(page.text)
        data.update({
            "login": creds.username,
            "password": creds.password,
            "requestAction": "eel",
            "codeType": "tryLogin",
            "codeValue": "login",
            "method": "extrainfo",
            "CurrentProgram": "skyportlogin.w",
        })
        if creds.security_code:
            data["securityCode"] = creds.security_code
        data.pop("cTrustDevice", None)   # never bind this machine as trusted
        data.setdefault("screenWidth", "1920")
        data.setdefault("screenHeight", "1080")

        r = self.http.post(self._url(LOGIN_POST), data=data, timeout=self.timeout)
        r.raise_for_status()
        tokens = parse_tokens(r.text)
        state = {k: v for k, v in inline_state(r.text).items()
                 if k in ("enc", "encses", "dwd", "nameid", "sessionid")}
        sid = token_session_id(tokens)
        if sid:
            state["sessionid"] = sid
        # The reply itself carries fresh enc/encses; prefer it over the form's.
        for k in ("enc", "encses"):
            if tokens.get(k):
                state[k] = tokens[k]
        self.session = Session(tokens=tokens, state=state)
        self._cache.clear()
        return self.session

    # ── pages ────────────────────────────────────────────────────────────

    def fetch(self, page: str, data: dict[str, Any] | None = None,
              refresh: bool = False) -> str:
        """POST a page and return its HTML, keeping the inline state current."""
        if self.session is None:
            raise LoginError("not logged in")
        key = page + "|" + repr(sorted((data or {}).items()))
        if not refresh and key in self._cache:
            return self._cache[key]
        payload = self.session.payload(page, data, ajax=page.startswith("httploader"))
        r = self.http.post(self._url(page), data=payload, timeout=self.timeout)
        r.raise_for_status()
        body = r.text
        if _is_login_page(body):
            raise SessionExpired("Skyward returned the login page; the session ended mid-run")
        if "Unable to run web object file" in body or "<BR>Unable to" in body:
            raise SkywardError(f"Skyward rejected the request for {page}")
        st = inline_state(body)
        if st.get("sessionid"):
            self.session.state["sessionid"] = st["sessionid"]
        if st.get("encses"):
            self.session.state["encses"] = st["encses"]
        if st.get("enc"):
            self.session.state["enc"] = st["enc"]
        self._cache[key] = body
        return body

    def gradebook(self, refresh: bool = False) -> str:
        return self.fetch(GRADEBOOK, refresh=refresh)

    def schedule(self, refresh: bool = False) -> str:
        return self.fetch(SCHEDULE, refresh=refresh)

    def attendance(self, refresh: bool = False) -> str:
        return self.fetch(ATTENDANCE, refresh=refresh)

    def home(self, refresh: bool = False) -> str:
        return self.fetch(HOME, refresh=refresh)

    def dialog(self, action: str, **fields: Any) -> str:
        """Hit an in-page dialog endpoint (e.g. GPA / class rank)."""
        return self.fetch(GRADEBOOK, {"action": action, "fromHttp": "yes", **fields})

    def ajax(self, page: str, **fields: Any) -> str:
        """Skyward's own AJAX call: POST httploader.p?file=<page>.

        This is what sff.request() does in the browser; dialogs (GPA, class
        rank, assignment details) only answer here. Needs `sessionid` from
        the page state, which the login reply and inline state provide.
        """
        extra = {"ishttp": "true", "requestId": str(len(self._cache) + 1)}
        extra.update(fields)
        return self.fetch("httploader.p?file=" + page, extra)

    def gpa(self) -> parse.GPA:
        st = parse.parse_student(self.gradebook())
        html_text = self.ajax(GRADEBOOK_DIALOG, action="viewGPARank",
                              stuId=st.student_id, entityId=st.entity_id)
        return parse.parse_gpa(html_text)


# ── token parsing ────────────────────────────────────────────────────────

def parse_tokens(response_text: str) -> dict[str, str]:
    """Turn the skyporthttp.w reply into a field map for subsequent pages.

    Success looks like '<li>dwd^webrecid^...^enc^encses^...</li>'; failure is
    '<li>Invalid login or password.</li>'. Unless it has >= 8 carets it's an
    error message we surface verbatim.
    """
    body = _html.unescape(re.sub(r"<[^>]+>", "", response_text)).strip()
    parts = body.split("^")
    if len(parts) < 8:
        msg = body.strip() or "login failed"
        if re.search(r"security|code|mfa|factor", msg, re.I):
            raise LoginError(f"{msg} (try --security-code)")
        raise LoginError(msg)
    tokens: dict[str, str] = {}
    for i, name in enumerate(TOKEN_NAMES):
        if i < len(parts) and parts[i] != "":
            tokens[name] = parts[i]
    tokens.setdefault("homepage", HOME)
    return tokens


def token_session_id(tokens: dict[str, str]) -> str:
    """sessionid the framework sends on AJAX calls (webrecid + wfaaclrecid)."""
    if tokens.get("webrecid") and tokens.get("wfaaclrecid"):
        return tokens["webrecid"] + tokens["wfaaclrecid"]
    return ""


def _is_login_page(body: str) -> bool:
    """Skyward quotes attributes with single quotes; match both."""
    has_pw = re.search(r"id=['\"]password['\"]", body)
    has_form = re.search(r"id=['\"]detailform['\"]", body)
    return bool(has_pw and has_form)


# ── credentials ──────────────────────────────────────────────────────────

def config_path() -> str:
    base = os.environ.get("SKYWARD_CONFIG_DIR") or os.path.expanduser("~/.config/skyward")
    return os.path.join(base, "config")


def load_config() -> dict[str, str]:
    """Read ~/.config/skyward/config (KEY=value lines, # comments)."""
    path = os.environ.get("SKYWARD_CONFIG") or config_path()
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip().lower()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def resolve_base(base: str | None = None) -> str:
    """CLI flag > SKYWARD_BASE (via typer's envvar) > config `base=` > placeholder."""
    cfg = load_config()
    return (base or cfg.get("base") or DEFAULT_BASE).strip()


def resolve_credentials(username: str | None = None, password: str | None = None,
                        security_code: str | None = None, prompt: bool = True) -> Credentials:
    """CLI flag > environment > config file > prompt.

    SKYWARD_USER, SKYWARD_PASS, SKYWARD_SECURITY_CODE also work, which keeps
    secrets out of shell history when you'd rather export them.
    """
    cfg = load_config()
    user = (username or os.environ.get("SKYWARD_USER") or cfg.get("username") or "").strip()
    pw = password or os.environ.get("SKYWARD_PASS") or cfg.get("password") or ""
    code = security_code or os.environ.get("SKYWARD_SECURITY_CODE") or cfg.get("security_code") or ""
    if prompt and not user:
        user = input("Skyward username: ").strip()
    if prompt and not pw:
        pw = getpass.getpass("Skyward password: ")
    if not user or not pw:
        raise LoginError(
            "no credentials: pass --user/--password, set SKYWARD_USER/SKYWARD_PASS, "
            f"or write {config_path()} with username=/password= lines"
        )
    return Credentials(username=user, password=pw, security_code=code)
