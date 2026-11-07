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

    if st.session_state["user"] is not None:
        user = st.session_state["user"]
        col1, col2 = st.columns([4, 1])
        col1.caption(f"👤 Sessão Ativa: **{user.email}**")
        if col2.button("Terminar Sessão", key="btn_logout"):
            supabase.auth.sign_out()
            st.session_state["user"] = None
            st.rerun()
        return user

    tab_login, tab_signup = st.tabs(["🔐 Iniciar Sessão", "📝 Criar Conta APEX"])
    
    with tab_login:
        if st.button("🌐 Iniciar Sessão com o Google", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_oauth({
                    "provider": "google",
                    "options": {
                        "redirect_to": "https://mae-engine.streamlit.app",
                        "queryParams": {
                            "prompt": "select_account"
                        }
                    }
                })
                if res.url:
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={res.url}">', unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Erro na autenticação com Google: {e}")

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
        if st.button("🌐 Criar Conta com o Google", use_container_width=True, key="btn_google_signup"):
            try:
                res = supabase.auth.sign_in_with_oauth({
                    "provider": "google",
                    "options": {
                        "redirect_to": "https://mae-engine.streamlit.app",
                        "queryParams": {
                            "prompt": "select_account"
                        }
                    }
                })
                if res.url:
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={res.url}">', unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Erro no registo com Google: {e}")

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
