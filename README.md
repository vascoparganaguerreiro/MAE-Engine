# Apex Engine — reescrita v6 local

Esta versão substitui a geração automática de dados fictícios por uma arquitetura **real-data-first**. Os módulos atuais foram mantidos, mas os dados são guardados localmente e os cálculos não preenchem medições ausentes com valores plausíveis.

## Ficheiros

- `app.py` — interface Streamlit e oito módulos.
- `engine_core.py` — cálculos puros, sem Streamlit ou rede.
- `data_store.py` — persistência SQLite de métricas, check-ins, treino, biomarcadores, provas, sapatilhas e perfil.
- `garmin_adapter.py` — sincronização pontual da Garmin Connect.
- `tests/test_engine.py` — testes essenciais para missing data, readiness, carga e cálculos.
- `requirements.txt` — dependências.

## Instalação local

Requer Python 3.12 ou superior (a versão atual de `garminconnect` requer Python 3.12+).

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
pytest -q
streamlit run app.py
```

A base de dados é criada automaticamente em `apex_data/apex.db`. Para escolher outro caminho, define `APEX_DB_PATH` antes de iniciar a aplicação. Faz backups regulares deste ficheiro.

## Gemini

A biblioteca `google-generativeai` foi substituída por `google-genai`.

Opção A — variável de ambiente:

```bash
# Windows PowerShell
$env:GEMINI_API_KEY="a_tua_chave"
# macOS/Linux
export GEMINI_API_KEY="a_tua_chave"
```

Opção B — cria `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "a_tua_chave"
GEMINI_MODEL = "gemini-3.8-flash"
```

O modelo predefinido é `gemini-3.8-flash`, atualmente listado como estável. O nome pode ser alterado em `GEMINI_MODEL` caso o fornecedor publique uma atualização ou retire o modelo.

## Garmin

A integração usa `python-garminconnect`, uma biblioteca de terceiros que acede à Garmin Connect por endpoints não oficiais. A Garmin pode alterar autenticação/endpoints e o funcionamento não é garantido. Introduz as credenciais apenas no formulário de sincronização; são usadas para uma tentativa de sync e limpas da sessão logo depois. O token temporário necessário à biblioteca é mantido numa pasta temporária privada e removido no fim da chamada; não é guardado na base SQLite nem num diretório persistente. Se a Garmin exigir MFA, esta versão mostra um erro e não completa ainda o segundo fator.

A sincronização é parcial por desenho: se um endpoint falhar, as restantes métricas ainda podem ser guardadas. Um campo ausente permanece vazio. A prontidão proprietária da Garmin é apresentada separadamente e não é misturada no score Apex.

## Regras de integridade dos dados

1. Não existe demo history no pipeline de produção. A app não mistura dados artificiais com dados pessoais.
2. Um campo em branco é `NULL`/ausente; não é convertido em 46 bpm, 64 ms, 85 pontos ou qualquer outro valor inventado.
3. Para CTL/ATL/TSB exigem-se 42 dias consecutivos explicitamente registados. Um dia de descanso tem de ser registado como `0 UA`; um dia em branco é desconhecido.
4. O ACWR só aparece com 28 dias consecutivos completos. É um descritor de carga, não um preditor individual validado de lesão.
5. O readiness Apex exige pelo menos dois sinais com linha de base pessoal suficiente. Os pesos e limites são heurísticos e ainda não foram validados prospectivamente.
6. Cargas de força estimadas só aparecem se o utilizador introduzir os seus 1RM. Não existem 1RM padrão fictícios.
7. Os biomarcadores podem usar limites de referência introduzidos pelo utilizador. Intervalos genéricos são apenas orientadores e não substituem os intervalos do laboratório nem avaliação clínica.
8. O score Healthspan é um composto educativo experimental; não representa idade biológica, prognóstico ou risco de doença.

## Segurança e privacidade — importante

- O código que enviaste continha uma palavra-passe Garmin hardcoded. Se era real, considera-a exposta e altera-a imediatamente. Não voltes a colocar credenciais no código, GitHub, screenshots ou mensagens.
- Esta é uma instalação **single-user/local**. O SQLite é um único ficheiro partilhado pelo processo. Não publiques esta aplicação para vários utilizadores nem recolhas dados de terceiros sem primeiro implementar autenticação, autorização, isolamento por utilizador, gestão de consentimentos, encriptação/backups e uma política de retenção adequada.
- Em alojamento cloud, confirma que o disco é persistente. Alguns ambientes podem apagar ficheiros locais quando a aplicação reinicia ou é redeployada.
- Não guardes `.streamlit/secrets.toml`, `apex_data/`, `.env` ou tokens no Git. O `.gitignore` incluído cobre estes caminhos.
- A aplicação não é um dispositivo médico. Sintomas de alarme exigem parar o exercício e procurar ajuda adequada, independentemente do score.

## Antes de voltar a publicar

Executa `pytest -q`, testa o fluxo manual sem Garmin, testa uma sincronização real com a Garmin, confirma o conteúdo de `apex_data/apex.db` e verifica o comportamento com dados incompletos. Esta entrega é uma base de trabalho funcional, não uma certificação clínica, auditoria de segurança ou garantia de compatibilidade perpétua com APIs externas.
