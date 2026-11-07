import os
import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = "https://quoafwluowkhjqqncnki.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY", "")

def get_supabase() -> Client:
    if "supabase_client" not in st.session_state:
        st.session_state["supabase_client"] = create_client(SUPABASE_URL, SUPABASE_KEY)
    return st.session_state["supabase_client"]

def render_login_component():
    supabase = get_supabase()
    
    if "user" not in st.session_state:
        st.session_state["user"] = None

    # 1. Se a sessão já estiver ativa no session_state, devolve o utilizador imediatamente
    if st.session_state["user"] is not None:
        return st.session_state["user"]

    # 2. Processar o código do Google OAuth se estiver presente no URL
    if "code" in st.query_params:
        auth_code = st.query_params["code"]
        # Limpa o URL antes de trocar o código para evitar re-exceções em re-runs
        st.query_params.clear()
        
        user_authenticated = None

        # Tentativa de troca por dicionário de parâmetros
        try:
            res = supabase.auth.exchange_code_for_session({"auth_code": auth_code})
            if res and getattr(res, "user", None):
                user_authenticated = res.user
            elif res and hasattr(res, "session") and res.session and getattr(res.session, "user", None):
                user_authenticated = res.session.user
        except Exception:
            pass

        # Tentativa de troca por string direta
        if not user_authenticated:
            try:
                res = supabase.auth.exchange_code_for_session(auth_code)
                if res and getattr(res, "user", None):
                    user_authenticated = res.user
                elif res and hasattr(res, "session") and res.session and getattr(res.session, "user", None):
                    user_authenticated = res.session.user
            except Exception:
                pass

        # Verificar se a sessão foi guardada no cliente Supabase
        if not user_authenticated:
            try:
                session = supabase.auth.get_session()
                if session and getattr(session, "user", None):
                    user_authenticated = session.user
            except Exception:
                pass

        if user_authenticated:
            st.session_state["user"] = user_authenticated
            st.rerun()

    # Re-verificar se a sessão ficou ativa após a troca
    if st.session_state["user"] is not None:
        return st.session_state["user"]

    # 3. Gerar a URL do Google OAuth
    oauth_url = None
    try:
        oauth_data = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": "https://mae-engine.streamlit.app",
                "queryParams": {"prompt": "select_account"}
            }
        })
        if oauth_data and hasattr(oauth_data, "url"):
            oauth_url = oauth_data.url
    except Exception:
        pass

    # 4. Interface de Autenticação (Executive Design System)
    tab_login, tab_signup = st.tabs(["🔐 INICIAR SESSÃO", "📝 CRIAR CONTA"])
    
    with tab_login:
        if oauth_url:
            st.link_button("🌐 INICIAR SESSÃO COM O GOOGLE", oauth_url, use_container_width=True)
        else:
            st.error("Erro ao gerar ligação do Google OAuth.")

        st.markdown("<div style='text-align: center; color: #475569; margin: 15px 0; font-size: 0.75rem; letter-spacing: 1px;'>— OU UTILIZE O E-MAIL —</div>", unsafe_allow_html=True)

        with st.form("form_login"):
            email = st.text_input("E-mail")
            password = st.text_input("Palavra-passe", type="password")
            btn = st.form_submit_button("ENTRAR", use_container_width=True)
            if btn:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state["user"] = res.user
                    st.success("Sessão iniciada com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao iniciar sessão: {e}")

    with tab_signup:
        if oauth_url:
            st.link_button("🌐 CRIAR CONTA COM O GOOGLE", oauth_url, use_container_width=True, key="btn_google_signup")

        st.markdown("<div style='text-align: center; color: #475569; margin: 15px 0; font-size: 0.75rem; letter-spacing: 1px;'>— OU REGISTE-SE COM E-MAIL —</div>", unsafe_allow_html=True)

        with st.form("form_signup"):
            new_email = st.text_input("E-mail para nova conta")
            new_password = st.text_input("Definir palavra-passe", type="password")
            full_name = st.text_input("Nome completo")
            btn_sub = st.form_submit_button("CRIAR CONTA SEGURA", use_container_width=True)
            if btn_sub:
                try:
                    res = supabase.auth.sign_up({
                        "email": new_email,
                        "password": new_password,
                        "options": {"data": {"full_name": full_name}}
                    })
                    st.success("Conta criada com sucesso. Verifique o seu e-mail.")
                except Exception as e:
                    st.error(f"Erro no registo: {e}")

    return None
