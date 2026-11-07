import os
import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = "https://quoafwluowkhjqqncnki.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY", "")

def get_supabase_client() -> Client:
    """
    Guarda o cliente Supabase no session_state individual do utilizador.
    NÃO utiliza @st.cache_resource para preservar o 'code_verifier' do OAuth PKCE.
    """
    if "supabase_client" not in st.session_state:
        st.session_state["supabase_client"] = create_client(SUPABASE_URL, SUPABASE_KEY)
    return st.session_state["supabase_client"]

def render_login_component():
    supabase = get_supabase_client()
    
    if "user" not in st.session_state:
        st.session_state["user"] = None

    # Se a sessão já estiver ativa, devolve o utilizador imediatamente
    if st.session_state["user"] is not None:
        return st.session_state["user"]

    # 1. Processar o parâmetro 'code' devolvido pelo Google OAuth no URL
    query_params = st.query_params
    if "code" in query_params:
        auth_code = query_params["code"]
        st.query_params.clear()
        
        try:
            res = None
            try:
                res = supabase.auth.exchange_code_for_session({"auth_code": auth_code})
            except Exception:
                try:
                    res = supabase.auth.exchange_code_for_session(auth_code)
                except Exception:
                    pass

            if res and getattr(res, 'user', None):
                st.session_state["user"] = res.user
            elif res and hasattr(res, 'session') and res.session and getattr(res.session, 'user', None):
                st.session_state["user"] = res.session.user
            else:
                session = supabase.auth.get_session()
                if session and getattr(session, 'user', None):
                    st.session_state["user"] = session.user

            if st.session_state["user"] is not None:
                st.rerun()

        except Exception as e:
            st.warning(f"Aviso de autenticação: {e}")

    # 2. Verificar se já existe uma sessão ativa no cliente
    try:
        session = supabase.auth.get_session()
        if session and getattr(session, 'user', None):
            st.session_state["user"] = session.user
            return session.user
    except Exception:
        pass

    # 3. Interface de Autenticação (Executive Design System)
    tab_login, tab_signup = st.tabs(["🔐 INICIAR SESSÃO", "📝 CRIAR CONTA"])
    
    with tab_login:
        try:
            oauth_data = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": "https://mae-engine.streamlit.app",
                    "queryParams": {"prompt": "select_account"}
                }
            })
            if oauth_data and oauth_data.url:
                st.link_button("🌐 INICIAR SESSÃO COM O GOOGLE", oauth_data.url, use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao gerar ligação Google: {e}")

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
        try:
            oauth_data = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": "https://mae-engine.streamlit.app",
                    "queryParams": {"prompt": "select_account"}
                }
            })
            if oauth_data and oauth_data.url:
                st.link_button("🌐 CRIAR CONTA COM O GOOGLE", oauth_data.url, use_container_width=True, key="btn_google_signup")
        except Exception as e:
            st.error(f"Erro ao gerar ligação Google: {e}")

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
