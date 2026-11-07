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

    # Capturar e trocar o código de autorização do Google OAuth
    query_params = st.query_params
    if "code" in query_params and st.session_state["user"] is None:
        auth_code = query_params["code"]
        try:
            res = supabase.auth.exchange_code_for_session({"auth_code": auth_code})
            if res and res.user:
                st.session_state["user"] = res.user
            elif res and res.session:
                st.session_state["user"] = res.session.user
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            # Caso o código já tenha sido trocado ou expirado num reload anterior
            try:
                session = supabase.auth.get_session()
                if session and session.user:
                    st.session_state["user"] = session.user
                    st.query_params.clear()
                    st.rerun()
            except Exception:
                pass

    if st.session_state["user"] is not None:
        user = st.session_state["user"]
        col1, col2 = st.columns([4, 1])
        col1.caption(f"👤 Sessão Ativa: **{user.email}**")
        if col2.button("Terminar Sessão", key="btn_logout"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            st.session_state["user"] = None
            st.query_params.clear()
            st.rerun()
        return user

    tab_login, tab_signup = st.tabs(["🔐 Iniciar Sessão", "📝 Criar Conta APEX"])
    
    with tab_login:
        try:
            res = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": "https://mae-engine.streamlit.app",
                    "queryParams": {"prompt": "select_account"}
                }
            })
            if res.url:
                st.link_button("🌐 Iniciar Sessão com o Google", res.url, use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao ligar ao Google: {e}")

        st.markdown("<div style='text-align: center; color: #64748b; margin: 10px 0;'>— ou usa o teu e-mail —</div>", unsafe_allow_html=True)

        with st.form("form_login"):
            email = st.text_input("E-mail")
            password = st.text_input("Palavra-passe", type="password")
            btn = st.form_submit_button("Entrar", use_container_width=True)
            if btn:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state["user"] = res.user
                    st.success("Sessão iniciada!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao iniciar sessão: {e}")

    with tab_signup:
        try:
            res = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": "https://mae-engine.streamlit.app",
                    "queryParams": {"prompt": "select_account"}
                }
            })
            if res.url:
                st.link_button("🌐 Criar Conta com o Google", res.url, use_container_width=True, key="btn_google_signup")
        except Exception as e:
            st.error(f"Erro ao ligar ao Google: {e}")

        st.markdown("<div style='text-align: center; color: #64748b; margin: 10px 0;'>— ou regista-te com e-mail —</div>", unsafe_allow_html=True)

        with st.form("form_signup"):
            new_email = st.text_input("E-mail para nova conta")
            new_password = st.text_input("Escolhe uma palavra-passe", type="password")
            full_name = st.text_input("Nome completo")
            btn_sub = st.form_submit_button("Criar Conta Segura (UE)", use_container_width=True)
            if btn_sub:
                try:
                    res = supabase.auth.sign_up({
                        "email": new_email,
                        "password": new_password,
                        "options": {"data": {"full_name": full_name}}
                    })
                    st.success("Conta criada com sucesso! Verifica o teu e-mail ou faz login.")
                except Exception as e:
                    st.error(f"Erro no registo: {e}")

    return None
