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
ALLOWED_EMAILS = "o.teu@email.com"          # obrigatório para restringir o acesso; várias: separadas por vírgula
GEMINI_API_KEY = "..."
```

`ALLOWED_EMAILS` é obrigatório numa app privada. Sem esta lista, o registo público pode permitir que qualquer pessoa crie uma conta. Para um deployment privado, inclui apenas os emails autorizados. Não coloques chaves `service_role` no browser nem no repositório.

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

## Expandir os dados Garmin (executar uma vez)

Antes de usar esta versão, abre `supabase_garmin_metrics_migration.sql` no SQL Editor do Supabase e executa a migração. Ela acrescenta campos nullable para sono, fases do sono, HRV, frequência cardíaca, stress, Body Battery, SpO₂, respiração, passos, calorias, readiness e métricas de atividade. Não executa esta migração em produção sem primeiro confirmar que tens backup.

A sincronização usa a biblioteca comunitária `garminconnect` (não oficial). Os endpoints variam com o dispositivo, sensores, firmware, região, conta e dados sincronizados. A app tenta recolher, quando devolvidos pela conta: HRV noturna e média semanal; FC repouso e médias; duração/meta/score/fases do sono; Garmin Training Readiness e fatores disponíveis; stress; Body Battery; respiração; SpO₂; passos; distância; pisos; calorias; minutos de intensidade; hidratação; estado e foco da carga; VO₂max de corrida/ciclismo; FTP; limiar de lactato; economia de corrida; endurance score; e métricas das atividades (duração, distância, carga, FC, potência, cadência e dinâmica quando o resumo Garmin as inclui). As médias de sono de 7 e 28 noites são calculadas a partir dos registos diários válidos guardados pelo Apex.

Isto **não equivale a garantir literalmente todas as métricas Garmin**. O wrapper disponibiliza muitos endpoints, mas cada utilizador só recebe os campos que a Garmin disponibiliza para a conta, dispositivo, sensores, atividade, firmware, permissões e região. Alguns dados detalhados de atividade, zonas, curvas e sensores podem exigir chamadas adicionais ou exportação FIT; não devem ser mostrados como disponíveis quando não foram devolvidos. A página "All available Garmin metrics" identifica os campos sem registo. VO₂max de ciclismo, dinâmica avançada de corrida e potência dependem de sensores e atividades compatíveis. As métricas de atividade individuais são guardadas separadamente.

A versão comunitária requer Python 3.12 ou superior. Para produtos comerciais ou uma plataforma multiutilizador com integração Garmin, consulta o Garmin Connect Developer Program; a Personal API destina-se aos dados do próprio utilizador e não a aplicações comerciais com vários utilizadores.

## Correr localmente

```bash
pip install -r requirements.txt
pytest -q
streamlit run app.py      # Secrets locais em .streamlit/secrets.toml (já está no .gitignore)
```

## Limitações conhecidas

- A sessão vive no browser: ao atualizar a página é preciso iniciar sessão de novo (para persistir, usar `st.login` nativo ou um componente de cookies). Se a Garmin pedir MFA, introduz o código temporário no campo apresentado; o estado MFA contém cookies de sessão e permanece apenas em memória na sessão Streamlit até concluir ou abandonar a autenticação.
- Definições (idioma, modo, perfil) ficam na sessão e repõem-se ao atualizar; persistir exige uma tabela `user_settings`.
- A Garmin Connect é acedida por uma biblioteca não oficial e pode mudar sem aviso. Nem todos os campos existem para todos os dispositivos/contas. O fluxo de MFA apresenta um campo para o código de verificação; o estado temporário da autenticação fica apenas na sessão do utilizador e deve ser eliminado após a conclusão.
- O token Garmin é material de autenticação sensível e fica em `~/.cache/apex-engine/garmin/` por utilizador Apex; protege a conta do sistema operativo e nunca comites esse diretório.
- Não apresentes esta aplicação a outros utilizadores até configurares `ALLOWED_EMAILS`, confirmares as políticas RLS e obteres o modelo de acesso Garmin adequado ao uso pretendido.
