import os
import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = "https://quoafwluowkhjqqncnki.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY", "")

@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def render_login_component():
    supabase = get_supabase_client()
    
    if "user" not in st.session_state:
        st.session_state["user"] = None

    # Se já existir utilizador na sessão, retorna-o diretamente
    if st.session_state["user"] is not None:
        return st.session_state["user"]

    # Capturar e trocar o código de autorização do Google OAuth do URL
    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        try:
            response = supabase.auth.exchange_code_for_session(code)
            if response and getattr(response, 'user', None):
                st.session_state["user"] = response.user
            elif response and hasattr(response, 'session') and response.session:
                st.session_state["user"] = response.session.user
            
            # Limpa o URL para remover o código e faz rerun para entrar na app
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erro na autenticação Google: {e}")

    # Verificar sessão ativa existente no cliente Supabase
    try:
        session = supabase.auth.get_session()
        if session and session.user:
            st.session_state["user"] = session.user
            return session.user
    except Exception:
        pass

    # Ecrã de Login / Registo com Design Luxury
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
            st.error(f"Erro ao ligar ao Google: {e}")

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
            st.error(f"Erro ao ligar ao Google: {e}")

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
                    st.success("Conta criada. Verifique o seu e-mail.")
                except Exception as e:
                    st.error(f"Erro no registo: {e}")

    return None
