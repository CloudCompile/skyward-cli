"""Client tests: login protocol, session handling and config resolution."""

import pytest

from fake_skyward import PASSWORD, TOKENS, USER, FakeSkyward

SID = TOKENS[1] + TOKENS[2]
from skyward import client as sky


@pytest.fixture
def fake():
    with FakeSkyward() as f:
        yield f


@pytest.fixture
def c(fake):
    return sky.SkywardClient(base=fake.base)


def test_login_posts_tokens_to_skyporthttp(c, fake):
    c.login(sky.Credentials(USER, PASSWORD))
    login_posts = [r for r in fake.requests if r[1].endswith("skyporthttp.w")]
    assert len(login_posts) == 1
    form = login_posts[0][2]
    # fields the real portal requires to accept a POST as a login attempt
    assert form["requestAction"][0] == "eel"
    assert form["codeType"][0] == "tryLogin"
    assert form["hAnon"][0] == "aN0nT0k3n"
    assert "cTrustDevice" not in form, "never trust the device silently"
    assert c.session.tokens["nameid"] == "111111"
    assert c.session.state["sessionid"] == SID


def test_wrong_password_raises_with_portal_message(c, fake):
    with pytest.raises(sky.LoginError) as e:
        c.login(sky.Credentials(USER, "nope"))
    assert "Invalid login or password" in str(e.value)


def test_security_code_prompt_is_detected(fake):
    c = sky.SkywardClient(base=fake.base)
    with pytest.raises(sky.LoginError) as e:
        c.login(sky.Credentials(USER, PASSWORD, security_code="MFA"))
    assert "security code" in str(e.value).lower()


def test_session_expiry_is_detected(c, fake):
    c.login(sky.Credentials(USER, PASSWORD))
    fake.logged_in = False          # portal forgets us mid-run
    with pytest.raises(sky.SessionExpired):
        c.fetch("sfgradebook001.w", refresh=True)


def test_fetch_before_login_raises(c):
    with pytest.raises(sky.LoginError):
        c.fetch("sfgradebook001.w")


def test_fetch_round_trips_state_and_caches(c, fake):
    c.login(sky.Credentials(USER, PASSWORD))
    a = c.gradebook()
    b = c.gradebook()
    assert a is b, "second call should come from cache"
    posts = [r for r in fake.requests if r[1].endswith("sfgradebook001.w")]
    assert len(posts) == 1
    assert posts[0][2]["pg"] == ["sfgradebook001.w"]
    assert posts[0][2]["dwd"] == ["1001"]
    assert "sessionid" not in posts[0][2], "forms reject the AJAX-only sessionid"


def test_ajax_sends_sessionid_and_can_fetch_gpa(c, fake):
    c.login(sky.Credentials(USER, PASSWORD))
    gpa = c.gpa()
    assert gpa.unweighted == 3.75
    assert gpa.rank == "42 of 310"
    ajax = [r for r in fake.requests if "httploader.p" in r[1]]
    assert ajax, "gpa should go through httploader.p"
    assert ajax[-1][2]["sessionid"] == [SID]
    assert ajax[-1][2]["ishttp"] == ["true"]


def test_parse_tokens_success_and_failure():
    tok = sky.parse_tokens("<li>1^2^3^4^5^u^2^sfhome01.w^false^no ^no^no^^enc^ses^lhi</li>")
    assert tok["nameid"] == "5" and tok["enc"] == "enc" and tok["encses"] == "ses"
    assert tok["duserid"] == "u"
    with pytest.raises(sky.LoginError):
        sky.parse_tokens("<li>Invalid login or password.</li>")
    with pytest.raises(sky.LoginError):
        sky.parse_tokens("")


def test_token_session_id():
    assert sky.token_session_id({"webrecid": "a", "wfaaclrecid": "b"}) == "ab"
    assert sky.token_session_id({}) == ""


def test_resolve_credentials_precedence(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.write_text("username=fromfile\npassword=filepw\n# comment\nsecurity_code=99\n")
    monkeypatch.setenv("SKYWARD_CONFIG", str(cfg))
    monkeypatch.delenv("SKYWARD_USER", raising=False)
    creds = sky.resolve_credentials(prompt=False)
    assert (creds.username, creds.password, creds.security_code) == ("fromfile", "filepw", "99")

    monkeypatch.setenv("SKYWARD_USER", "fromenv")
    assert sky.resolve_credentials("flaguser", prompt=False).username == "flaguser"
    assert sky.resolve_credentials(prompt=False).username == "fromenv"
    assert sky.resolve_credentials(prompt=False).password == "filepw"


def test_resolve_base_precedence(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.write_text("username=u\nbase=https://fromconfig.example/Sky/web/\n")
    monkeypatch.setenv("SKYWARD_CONFIG", str(cfg))
    assert sky.resolve_base() == "https://fromconfig.example/Sky/web/"
    assert sky.resolve_base("https://flag.example/Sky/web/") == "https://flag.example/Sky/web/"


def test_resolve_base_falls_back_to_placeholder(tmp_path, monkeypatch):
    """No config, no flag: a clearly fake URL, never a real district's."""
    monkeypatch.setenv("SKYWARD_CONFIG", str(tmp_path / "missing"))
    assert sky.resolve_base() == sky.DEFAULT_BASE
    assert "example.org" in sky.DEFAULT_BASE


def test_resolve_credentials_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SKYWARD_CONFIG", str(tmp_path / "missing"))
    monkeypatch.delenv("SKYWARD_USER", raising=False)
    monkeypatch.delenv("SKYWARD_PASS", raising=False)
    with pytest.raises(sky.LoginError) as e:
        sky.resolve_credentials(prompt=False)
    assert "no credentials" in str(e.value)


def test_base_url_normalisation():
    c = sky.SkywardClient(base="https://h.example/Sky/web")
    assert c.base == "https://h.example/Sky/web/"
    assert c._url("seplog01.w") == "https://h.example/Sky/web/seplog01.w"
    assert c._url("/Sky/web/x.w") == "https://h.example/Sky/web/x.w"
