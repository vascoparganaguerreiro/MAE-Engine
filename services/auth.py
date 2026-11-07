"""Login screen and session handling (Supabase: Google + e-mail/password).

Public API (unchanged for app.py): render_login_component() -> user | None
`user` is a services.supabase_auth.AuthUser with .id .email .full_name .access_token ...
"""
from __future__ import annotations

import time
from typing import Optional

import streamlit as st

from services import supabase_auth as sa
from services.config import get_secret

DEFAULT_SUPABASE_URL = "https://quoafwluowkhjqqncnki.supabase.co"
DEFAULT_APP_URL = "https://mae-engine.streamlit.app"
PKCE_REUSE_SECONDS = 480          # keep the same Google link while the page re-runs (verifier TTL is 600 s)
REFRESH_MARGIN_SECONDS = 120

_SESSION_KEYS = ("user", "_pkce", "_sb_client", "_sb_token", "_store_errors", "auth_error")
_SESSION_PREFIXES = ("setting_", "garmin_")   # per-user data must not survive a logout


def _supabase_url() -> str:
    return str(get_secret("SUPABASE_URL", DEFAULT_SUPABASE_URL))


def _app_url() -> str:
    return str(get_secret("APP_URL", DEFAULT_APP_URL)).rstrip("/")


def _allowed_emails() -> set:
    return sa.parse_allowed_emails(get_secret("ALLOWED_EMAILS", ""))


@st.cache_resource
def _pending_store() -> sa.PendingStore:
    """Process-wide on purpose: it must outlive the redirect to Google (a new browser session)."""
    return sa.PendingStore()


def _client() -> sa.SupabaseAuth:
    return sa.SupabaseAuth(_supabase_url(), str(get_secret("SUPABASE_KEY", "")))


def _clear_session() -> None:
    for key in list(st.session_state.keys()):
        if key in _SESSION_KEYS or str(key).startswith(_SESSION_PREFIXES):
            del st.session_state[key]


def _accept(user: sa.AuthUser) -> bool:
    problem = sa.access_error(user, _allowed_emails())
    if problem:
        st.session_state["auth_error"] = problem
        try:
            _client().sign_out(user.access_token)
        except sa.AuthError:
            pass
        return False
    st.session_state.pop("auth_error", None)
    st.session_state["user"] = user
    return True


def _google_url() -> str:
    """One stable Google link per browser session. It is only regenerated when it is about to expire,
    never on a normal re-run, so the verifier saved on the server always matches the link on screen."""
    pending = st.session_state.get("_pkce")
    now = time.time()
    if not pending or now - pending["t"] > PKCE_REUSE_SECONDS:
        verifier = sa.generate_verifier()
        pending = {"nonce": _pending_store().add(verifier), "challenge": sa.code_challenge(verifier), "t": now}
        st.session_state["_pkce"] = pending
    redirect_to = f"{_app_url()}/?s={pending['nonce']}"
    return _client().authorize_url(redirect_to, pending["challenge"], "google", {"prompt": "select_account"})


def _handle_oauth_return() -> None:
    """Runs first on every page load. When Google sends the browser back with ?code=..., finish the login."""
    params = st.query_params
    code, nonce = params.get("code"), params.get("s")
    problem = params.get("error_description") or params.get("error")
    if not (code or problem):
        return
    st.query_params.clear()                       # never leave the one-time code in the address bar
    if st.session_state.get("user") is not None:
        return
    if problem and not code:
        st.session_state["auth_error"] = f"O início de sessão foi cancelado ou recusado ({problem})."
        return
    try:
        user = sa.complete_oauth(_client(), _pending_store(), str(code), str(nonce) if nonce else None)
    except sa.AuthError as exc:
        st.session_state["auth_error"] = exc.message
        return
    if _accept(user):
        st.rerun()


def _keep_session_fresh(user: sa.AuthUser) -> sa.AuthUser:
    """Access tokens last about an hour; renew them quietly so data calls keep working."""
    if not user.expires_at or not user.refresh_token or user.expires_at - time.time() > REFRESH_MARGIN_SECONDS:
        return user
    try:
        fresh = _client().refresh(user.refresh_token)
    except sa.AuthError:
        _clear_session()
        st.session_state["auth_error"] = "A sessão expirou. Inicia sessão novamente."
        st.rerun()
        return user
    st.session_state["user"] = fresh
    return fresh


def _logout(user: sa.AuthUser) -> None:
    try:
        _client().sign_out(user.access_token)
    except sa.AuthError:
        pass
    _clear_session()
    st.query_params.clear()
    st.rerun()


def render_login_component() -> Optional[sa.AuthUser]:
    _handle_oauth_return()
    user = st.session_state.get("user")

    if user is not None:
        user = _keep_session_fresh(user)
        col1, col2 = st.columns([4, 1])
        col1.caption(f"👤 Sessão Ativa: **{user.email}**")
        if col2.button("Terminar Sessão", key="btn_logout"):
            _logout(user)
        if not _allowed_emails():
            st.warning("⚠️ Qualquer pessoa que crie conta consegue entrar nesta app. "
                       "Define ALLOWED_EMAILS nos Secrets para restringir o acesso.")
        return user

    error = st.session_state.pop("auth_error", None)
    if error:
        st.error(error)

    try:
        google_url = _google_url()
    except sa.AuthError as exc:
        google_url = None
        st.error(exc.message)

    tab_login, tab_signup = st.tabs(["🔐 Iniciar Sessão", "📝 Criar Conta APEX"])

    with tab_login:
        if google_url:
            st.link_button("🌐 Iniciar Sessão com o Google", google_url, use_container_width=True, key="btn_google_login")
            st.caption("O Google abre num novo separador; depois de aceitares, a app abre aí já com a sessão iniciada.")
        st.markdown("<div style='text-align: center; color: #64748b; margin: 10px 0;'>— ou usa o teu e-mail —</div>",
                    unsafe_allow_html=True)
        with st.form("form_login"):
            email = st.text_input("E-mail")
            password = st.text_input("Palavra-passe", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                try:
                    signed = _client().sign_in_password(email, password)
                except sa.AuthError as exc:
                    st.error(exc.message)
                else:
                    if _accept(signed):
                        st.rerun()
                    else:
                        st.error(st.session_state.pop("auth_error", "Acesso negado."))

    with tab_signup:
        if google_url:
            st.link_button("🌐 Criar Conta com o Google", google_url, use_container_width=True, key="btn_google_signup")
        st.markdown("<div style='text-align: center; color: #64748b; margin: 10px 0;'>— ou regista-te com e-mail —</div>",
                    unsafe_allow_html=True)
        with st.form("form_signup"):
            new_email = st.text_input("E-mail para nova conta")
            new_password = st.text_input("Escolhe uma palavra-passe", type="password")
            full_name = st.text_input("Nome completo")
            if st.form_submit_button("Criar Conta Segura (UE)", use_container_width=True):
                try:
                    result = _client().sign_up(new_email, new_password, full_name)
                except sa.AuthError as exc:
                    st.error(exc.message)
                else:
                    st.success("Conta criada! Verifica o teu e-mail para confirmar e depois inicia sessão."
                               if result["needs_confirmation"] else "Conta criada! Já podes iniciar sessão.")
    return None
