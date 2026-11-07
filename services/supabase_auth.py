"""Supabase (GoTrue) authentication over plain REST - no Streamlit, no hidden shared state.

Why this exists
---------------
Google login with Supabase uses PKCE: before leaving for Google we create a secret
`code_verifier`; when Google sends the browser back with `?code=...` we must present the SAME
verifier to exchange the code for a session. In Streamlit the redirect is a brand new browser
session, so the verifier has to be kept on the server between the two requests (PendingStore).

The old implementation lost the login because
  1. it called `exchange_code_for_session(code)` with a string (the API expects a dict),
  2. it created a new verifier on every render (twice per render: login tab + sign-up tab),
     overwriting the one the Google button was built with,
  3. all visitors shared one cached client (one visitor could inherit another's session).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import string
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

HttpFn = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, bytes]]


class AuthError(Exception):
    """`message` is safe to show to the user (never contains secrets)."""

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    full_name: str = ""
    email_confirmed: bool = False
    access_token: str = field(default="", repr=False)
    refresh_token: str = field(default="", repr=False)
    expires_at: float = 0.0


# ─────────────────────────── PKCE ───────────────────────────
_VERIFIER_CHARS = string.ascii_letters + string.digits + "-._~"


def generate_verifier(length: int = 64) -> str:
    if not 43 <= length <= 128:
        raise ValueError("PKCE verifier length must be between 43 and 128")
    return "".join(secrets.choice(_VERIFIER_CHARS) for _ in range(length))


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class PendingStore:
    """Server-side memory of logins that left for Google and have not come back yet.

    Keyed by an unguessable nonce that travels in the redirect URL. Entries expire (default 10 min)
    and are single-use. Lives in process memory: if the server restarts mid-login, the user simply
    clicks the button again.
    """

    def __init__(self, ttl: float = 600.0, max_items: int = 500, clock: Callable[[], float] = time.time):
        self._ttl, self._max, self._clock = ttl, max_items, clock
        self._items: Dict[str, Tuple[str, float]] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = self._clock()
        for key in [k for k, (_, t) in self._items.items() if now - t > self._ttl]:
            del self._items[key]
        while len(self._items) > self._max:
            del self._items[next(iter(self._items))]

    def add(self, verifier: str) -> str:
        nonce = secrets.token_urlsafe(16)
        with self._lock:
            self._purge()
            self._items[nonce] = (verifier, self._clock())
        return nonce

    def pop(self, nonce: str) -> Optional[str]:
        with self._lock:
            self._purge()
            item = self._items.pop(nonce, None)
        return item[0] if item else None

    def discard(self, nonce: str) -> None:
        with self._lock:
            self._items.pop(nonce, None)

    def recent(self, limit: int = 5) -> List[Tuple[str, str]]:
        """Newest first. Used only when the nonce got lost on the way back from Google."""
        with self._lock:
            self._purge()
            return [(k, v[0]) for k, v in reversed(list(self._items.items()))][:limit]

    def __len__(self) -> int:
        with self._lock:
            self._purge()
            return len(self._items)


# ─────────────────────────── HTTP + errors ───────────────────────────
def _default_http(method: str, url: str, headers: Dict[str, str], body: Optional[bytes]) -> Tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - https URL from config
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AuthError("Não foi possível contactar o serviço de autenticação. Verifica a ligação e tenta de novo.",
                        "network") from exc


def _error_from(status: int, payload: Any) -> AuthError:
    text = ""
    if isinstance(payload, dict):
        text = " ".join(str(payload.get(k, "")) for k in ("error_code", "error", "error_description", "msg", "message")).lower()
    if "invalid login credentials" in text or "invalid_credentials" in text:
        return AuthError("E-mail ou palavra-passe incorretos.", "invalid_credentials")
    if "email not confirmed" in text or "email_not_confirmed" in text:
        return AuthError("Confirma o teu e-mail antes de entrar (verifica a caixa de entrada).", "email_not_confirmed")
    if "already registered" in text or "user_already_exists" in text or "already been registered" in text:
        return AuthError("Já existe uma conta com este e-mail.", "user_exists")
    if "code challenge" in text or "code verifier" in text or "flow state" in text or "flow_state" in text:
        return AuthError("O pedido de login expirou ou já foi usado. Tenta de novo.", "verifier_mismatch")
    if "weak_password" in text or "password should be" in text:
        return AuthError("A palavra-passe é demasiado fraca (usa pelo menos 8 caracteres).", "weak_password")
    if status == 429 or "rate limit" in text or "rate_limit" in text:
        return AuthError("Demasiadas tentativas. Espera um minuto e tenta de novo.", "rate_limited")
    if status in (401, 403):
        return AuthError("Sem autorização para esta operação.", "unauthorized")
    return AuthError(f"Erro do serviço de autenticação (HTTP {status}).", "http_error")


# ─────────────────────────── client ───────────────────────────
class SupabaseAuth:
    """Stateless client: every call is explicit, nothing is stored between calls."""

    def __init__(self, url: str, anon_key: str, http: Optional[HttpFn] = None,
                 clock: Callable[[], float] = time.time):
        if not url or not anon_key:
            raise AuthError("Configuração em falta: define SUPABASE_KEY nos Secrets da app.", "config")
        self._base = url.rstrip("/") + "/auth/v1"
        self._key = anon_key
        self._http = http or _default_http
        self._clock = clock

    def _call(self, method: str, path: str, *, query: Optional[Dict[str, str]] = None,
              body: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Any:
        url = self._base + path + (("?" + urllib.parse.urlencode(query)) if query else "")
        headers = {"apikey": self._key, "Content-Type": "application/json",
                   "Authorization": f"Bearer {token or self._key}"}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        status, raw = self._http(method, url, headers, data)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            payload = {}
        if status >= 400:
            raise _error_from(status, payload)
        return payload

    def _user_from(self, payload: Dict[str, Any]) -> AuthUser:
        user = payload.get("user") or {}
        access = str(payload.get("access_token") or "")
        if not user and access:
            user = self._call("GET", "/user", token=access)
        if not isinstance(user, dict) or not user.get("id") or not user.get("email"):
            raise AuthError("A resposta de autenticação não trouxe os dados do utilizador.", "bad_response")
        meta = user.get("user_metadata") or {}
        expires_at = float(payload.get("expires_at") or 0) or (self._clock() + float(payload.get("expires_in") or 3600))
        return AuthUser(
            id=str(user["id"]), email=str(user["email"]),
            full_name=str(meta.get("full_name") or meta.get("name") or ""),
            email_confirmed=bool(user.get("email_confirmed_at") or user.get("confirmed_at")),
            access_token=access, refresh_token=str(payload.get("refresh_token") or ""), expires_at=expires_at)

    # -- Google (PKCE) -----------------------------------------------------------
    def authorize_url(self, redirect_to: str, challenge: str, provider: str = "google",
                      extra: Optional[Dict[str, str]] = None) -> str:
        query = {"provider": provider, "redirect_to": redirect_to,
                 "code_challenge": challenge, "code_challenge_method": "s256"}
        query.update(extra or {})
        return f"{self._base}/authorize?{urllib.parse.urlencode(query)}"

    def exchange_code(self, auth_code: str, verifier: str) -> AuthUser:
        payload = self._call("POST", "/token", query={"grant_type": "pkce"},
                             body={"auth_code": auth_code, "code_verifier": verifier})
        return self._user_from(payload)

    # -- e-mail / password -------------------------------------------------------
    def sign_in_password(self, email: str, password: str) -> AuthUser:
        if not email.strip() or not password:
            raise AuthError("Preenche o e-mail e a palavra-passe.", "missing_fields")
        payload = self._call("POST", "/token", query={"grant_type": "password"},
                             body={"email": email.strip(), "password": password})
        return self._user_from(payload)

    def sign_up(self, email: str, password: str, full_name: str = "") -> Dict[str, Any]:
        if not email.strip() or not password:
            raise AuthError("Preenche o e-mail e a palavra-passe.", "missing_fields")
        payload = self._call("POST", "/signup", body={"email": email.strip(), "password": password,
                                                       "data": {"full_name": full_name.strip()}})
        if payload.get("access_token"):
            return {"user": self._user_from(payload), "needs_confirmation": False}
        return {"user": None, "needs_confirmation": True}

    # -- session -----------------------------------------------------------------
    def refresh(self, refresh_token: str) -> AuthUser:
        payload = self._call("POST", "/token", query={"grant_type": "refresh_token"},
                             body={"refresh_token": refresh_token})
        return self._user_from(payload)

    def sign_out(self, access_token: str) -> None:
        """Best effort: only this device's session is revoked (scope=local)."""
        try:
            self._call("POST", "/logout", query={"scope": "local"}, token=access_token)
        except AuthError:
            pass


# ─────────────────────────── flow helpers ───────────────────────────
def complete_oauth(auth: SupabaseAuth, pending: PendingStore, code: str, nonce: Optional[str] = None,
                   max_fallback: int = 5) -> AuthUser:
    """Finish a Google login using the verifier saved before the redirect.

    With the nonce (normal case) exactly one verifier is used. If the nonce was lost (Supabase
    redirect allow-list stripped the query string) the newest pending verifiers are tried; a wrong
    verifier is rejected by Supabase without consuming the code.
    """
    if not code:
        raise AuthError("A resposta do Google não trouxe o código de autorização.", "no_code")
    candidates: List[Tuple[str, str, bool]] = []
    if nonce:
        verifier = pending.pop(nonce)
        if verifier:
            candidates.append((nonce, verifier, True))
    if not candidates:
        candidates = [(n, v, False) for n, v in pending.recent(max_fallback)]
    if not candidates:
        raise AuthError("O pedido de login expirou (passaram mais de 10 minutos ou o servidor reiniciou). "
                        "Clica de novo em Iniciar Sessão com o Google.", "pending_expired")
    last: Optional[AuthError] = None
    for key, verifier, exact in candidates:
        try:
            user = auth.exchange_code(code, verifier)
        except AuthError as exc:
            last = exc
            if exact or exc.code != "verifier_mismatch":
                raise
            continue
        pending.discard(key)
        return user
    assert last is not None
    raise last


def parse_allowed_emails(raw: Any) -> Set[str]:
    if not raw:
        return set()
    items = raw if isinstance(raw, (list, tuple, set)) else re.split(r"[,;\s]+", str(raw))
    return {str(i).strip().lower() for i in items if str(i).strip()}


def access_error(user: AuthUser, allowed: Set[str]) -> Optional[str]:
    """None when the user may enter. Unconfirmed e-mails never count, otherwise anyone could
    register with somebody else's address and pass the allow-list."""
    if not user.email_confirmed:
        return "Confirma o teu e-mail antes de entrar (verifica a caixa de entrada)."
    if allowed and user.email.strip().lower() not in allowed:
        return "Esta conta não tem acesso ao APEX Engine."
    return None
