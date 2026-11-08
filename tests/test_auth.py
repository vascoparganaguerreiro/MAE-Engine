"""Login flow tests. They run against a fake Supabase server, so no network and no Streamlit are needed."""
import base64
import hashlib
import json
import urllib.parse

import pytest

from services import supabase_auth as sa

URL = "https://example.supabase.co"
KEY = "anon-key"


class FakeGoTrue:
    """Minimal imitation of the GoTrue endpoints the app uses, including PKCE verification."""

    def __init__(self):
        self.codes = {}          # auth_code -> code_challenge saved when the Google link was built
        self.calls = []
        self.confirmed = True

    def issue_code(self, challenge):
        code = f"code-{len(self.codes) + 1}"
        self.codes[code] = challenge
        return code

    def _session(self, email="ana@example.com"):
        return {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600,
                "user": {"id": "uid-1", "email": email, "email_confirmed_at": "2026-01-01" if self.confirmed else None,
                         "user_metadata": {"full_name": "Ana"}}}

    def http(self, method, url, headers, body):
        parsed = urllib.parse.urlparse(url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        data = json.loads(body) if body else {}
        path = parsed.path.replace("/auth/v1", "")
        self.calls.append((method, path, query, data, headers))
        assert headers["apikey"] == KEY
        grant = query.get("grant_type")
        if path == "/token" and grant == "pkce":
            if data.get("auth_code") not in self.codes:
                return 400, json.dumps({"error_code": "flow_state_not_found", "msg": "invalid flow state"}).encode()
            expected = self.codes[data["auth_code"]]
            digest = hashlib.sha256(data["code_verifier"].encode()).digest()
            if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != expected:
                return 400, json.dumps({"msg": "code challenge does not match previously saved code verifier"}).encode()
            return 200, json.dumps(self._session()).encode()
        if path == "/token" and grant == "password":
            if data == {"email": "ana@example.com", "password": "good-pass"}:
                return 200, json.dumps(self._session()).encode()
            if data["password"] == "unconfirmed":
                return 400, json.dumps({"error_code": "email_not_confirmed", "msg": "Email not confirmed"}).encode()
            if data["password"] == "spam":
                return 429, b"{}"
            return 400, json.dumps({"error_code": "invalid_credentials", "msg": "Invalid login credentials"}).encode()
        if path == "/token" and grant == "refresh_token":
            return (200, json.dumps(self._session()).encode()) if data["refresh_token"] == "RT" else (400, b"{}")
        if path == "/signup":
            return 200, json.dumps({"id": "uid-2", "email": data["email"]}).encode()
        if path == "/user":
            return 200, json.dumps(self._session()["user"]).encode()
        if path == "/logout":
            return 204, b""
        return 404, b"{}"


def make():
    server = FakeGoTrue()
    return server, sa.SupabaseAuth(URL, KEY, http=server.http, clock=lambda: 1000.0)


# ---------- PKCE ----------
def test_pkce_challenge_matches_rfc7636_example():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert sa.code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_verifier_is_long_random_and_url_safe():
    a, b = sa.generate_verifier(), sa.generate_verifier()
    assert a != b and 43 <= len(a) <= 128
    assert all(c.isalnum() or c in "-._~" for c in a)
    with pytest.raises(ValueError):
        sa.generate_verifier(10)


# ---------- pending store ----------
def test_pending_is_single_use():
    store = sa.PendingStore()
    nonce = store.add("verifier")
    assert store.pop(nonce) == "verifier"
    assert store.pop(nonce) is None


def test_pending_expires():
    now = [0.0]
    store = sa.PendingStore(ttl=600, clock=lambda: now[0])
    nonce = store.add("v")
    now[0] = 601
    assert store.pop(nonce) is None and len(store) == 0


def test_pending_recent_is_newest_first_and_capped():
    store = sa.PendingStore(max_items=3)
    for v in ["v1", "v2", "v3", "v4"]:
        store.add(v)
    assert [v for _, v in store.recent(5)] == ["v4", "v3", "v2"]


# ---------- Google login (the bug) ----------
def test_authorize_url_contains_pkce_parameters():
    _, auth = make()
    url = auth.authorize_url("https://app/?s=abc", "CHAL", "google", {"prompt": "select_account"})
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    assert url.startswith(URL + "/auth/v1/authorize?")
    assert q == {"provider": "google", "redirect_to": "https://app/?s=abc", "code_challenge": "CHAL",
                 "code_challenge_method": "s256", "prompt": "select_account"}


def test_exchange_sends_a_dict_with_code_and_verifier():
    server, auth = make()
    verifier = sa.generate_verifier()
    code = server.issue_code(sa.code_challenge(verifier))
    user = auth.exchange_code(code, verifier)
    method, path, query, body, _ = server.calls[-1]
    assert (method, path, query["grant_type"]) == ("POST", "/token", "pkce")
    assert body == {"auth_code": code, "code_verifier": verifier}
    assert user.email == "ana@example.com" and user.access_token == "AT" and user.expires_at == 4600.0


def test_login_survives_two_google_links_built_in_the_same_render():
    """Regression: the old code built the login-tab link and the sign-up-tab link separately, the second
    overwriting the verifier of the first, so the first button could never complete."""
    server, auth = make()
    pending = sa.PendingStore()
    v1, v2 = sa.generate_verifier(), sa.generate_verifier()
    n1, n2 = pending.add(v1), pending.add(v2)
    code_for_first_button = server.issue_code(sa.code_challenge(v1))
    user = sa.complete_oauth(auth, pending, code_for_first_button, nonce=n1)
    assert user.email == "ana@example.com"
    assert pending.pop(n1) is None and pending.pop(n2) == v2      # only the used one was consumed


def test_login_still_works_when_the_nonce_was_lost_on_redirect():
    server, auth = make()
    pending = sa.PendingStore()
    v_old, v_new = sa.generate_verifier(), sa.generate_verifier()
    pending.add(v_old)
    pending.add(v_new)
    code = server.issue_code(sa.code_challenge(v_old))
    assert sa.complete_oauth(auth, pending, code, nonce=None).id == "uid-1"
    assert [v for _, v in pending.recent()] == [v_new]


def test_unknown_nonce_without_pending_asks_to_retry():
    _, auth = make()
    with pytest.raises(sa.AuthError) as err:
        sa.complete_oauth(auth, sa.PendingStore(), "code-1", nonce="gone")
    assert err.value.code == "pending_expired"


def test_wrong_verifier_with_exact_nonce_fails_clearly():
    server, auth = make()
    pending = sa.PendingStore()
    nonce = pending.add(sa.generate_verifier())
    code = server.issue_code(sa.code_challenge(sa.generate_verifier()))   # challenge from another verifier
    with pytest.raises(sa.AuthError) as err:
        sa.complete_oauth(auth, pending, code, nonce=nonce)
    assert err.value.code == "verifier_mismatch"


def test_missing_code_is_reported():
    _, auth = make()
    with pytest.raises(sa.AuthError) as err:
        sa.complete_oauth(auth, sa.PendingStore(), "")
    assert err.value.code == "no_code"


# ---------- e-mail / password ----------
def test_password_login_ok():
    _, auth = make()
    assert auth.sign_in_password("ana@example.com", "good-pass").full_name == "Ana"


def test_password_errors_are_translated():
    _, auth = make()
    for password, code in [("bad", "invalid_credentials"), ("unconfirmed", "email_not_confirmed"), ("spam", "rate_limited")]:
        with pytest.raises(sa.AuthError) as err:
            auth.sign_in_password("ana@example.com", password)
        assert err.value.code == code


def test_empty_fields_do_not_hit_the_network():
    server, auth = make()
    with pytest.raises(sa.AuthError):
        auth.sign_in_password("", "x")
    assert server.calls == []


def test_sign_up_needs_confirmation_when_no_session_returned():
    _, auth = make()
    assert auth.sign_up("new@example.com", "long-password", "New")["needs_confirmation"] is True


def test_refresh_and_logout():
    server, auth = make()
    assert auth.refresh("RT").access_token == "AT"
    with pytest.raises(sa.AuthError):
        auth.refresh("stale")
    auth.sign_out("AT")
    assert server.calls[-1][1] == "/logout" and server.calls[-1][2] == {"scope": "local"}


def test_missing_configuration_is_a_friendly_error():
    with pytest.raises(sa.AuthError) as err:
        sa.SupabaseAuth(URL, "")
    assert err.value.code == "config"


def test_user_repr_never_contains_tokens():
    user = sa.AuthUser("1", "a@b.c", access_token="SECRET", refresh_token="SECRET2")
    assert "SECRET" not in repr(user)


# ---------- access control ----------
def test_allow_list_parsing():
    assert sa.parse_allowed_emails("A@x.com, b@x.com;\nc@x.com") == {"a@x.com", "b@x.com", "c@x.com"}
    assert sa.parse_allowed_emails(["A@x.com"]) == {"a@x.com"}
    assert sa.parse_allowed_emails("") == set()


def test_access_rules():
    ok = sa.AuthUser("1", "Ana@Example.com", email_confirmed=True)
    assert sa.access_error(ok, set()) is None
    assert sa.access_error(ok, {"ana@example.com"}) is None
    assert sa.access_error(ok, {"other@example.com"}) is not None
    unconfirmed = sa.AuthUser("2", "ana@example.com", email_confirmed=False)
    assert sa.access_error(unconfirmed, {"ana@example.com"}) is not None   # cannot pass with someone else's address
