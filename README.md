# Apex Engine

Performance & longevity app (Streamlit + Supabase + Garmin Connect).

## Ficheiros principais

| Ficheiro | Função |
|---|---|
| `app.py` | Arranque, login, pipeline de dados e dashboard |
| `services/supabase_auth.py` | Login por REST (Google PKCE + e-mail/palavra-passe), sem Streamlit, testável |
| `services/auth.py` | Ecrã de login e gestão da sessão |
| `services/config.py` | Leitura segura de Secrets / variáveis de ambiente |
| `data_store.py` | Dados por utilizador no Supabase (cliente autenticado por sessão) |
| `engine_core.py` | Cálculos puros (readiness, carga, tendências) |
| `tests/` | `pytest -q` (engine, login e data_store) |

## Secrets (Streamlit Cloud → App settings → Secrets)

```toml
SUPABASE_KEY   = "chave PUBLISHABLE/anon do Supabase (nunca a service_role)"
APP_URL        = "https://mae-engine.streamlit.app"
ALLOWED_EMAILS = "o.teu@email.com"          # várias: separadas por vírgula
GEMINI_API_KEY = "..."
```

`ALLOWED_EMAILS` é a proteção que impede que qualquer pessoa que crie conta veja os teus dados.

## Configuração do Supabase (Google login)

1. **Authentication → URL Configuration**: Site URL = `https://mae-engine.streamlit.app`; em *Redirect URLs* adiciona `https://mae-engine.streamlit.app/**`.
2. **Authentication → Sign In / Providers → Google**: ativo, com Client ID e Secret.
3. **Google Cloud Console → Credenciais → o teu cliente OAuth → URIs de redirecionamento autorizados**:
   `https://quoafwluowkhjqqncnki.supabase.co/auth/v1/callback`
4. **Row Level Security** (a app envia o token do utilizador; a base de dados passa a impor o isolamento):

```sql
alter table daily_telemetry   enable row level security;
alter table training_sessions enable row level security;
create policy "own rows" on daily_telemetry   for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own rows" on training_sessions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
-- necessário para o upsert (se ainda não existir):
alter table daily_telemetry add constraint daily_telemetry_user_date unique (user_id, date);
```

## Correr localmente

```bash
pip install -r requirements.txt
pytest -q
streamlit run app.py      # Secrets locais em .streamlit/secrets.toml (já está no .gitignore)
```

## Limitações conhecidas

- A sessão vive no browser: ao atualizar a página é preciso iniciar sessão de novo (para persistir, usar `st.login` nativo ou um componente de cookies).
- Definições (idioma, modo, perfil) ficam na sessão e repõem-se ao atualizar; persistir exige uma tabela `user_settings`.
- A Garmin Connect é acedida por uma biblioteca não oficial e pode mudar sem aviso; MFA ainda não é suportado.
