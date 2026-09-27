# AGENTS.md

Log de alterações feitas por agentes de IA neste repositório. Cada seção documenta o que foi
mudado, por quê, e as ressalvas que quem for evoluir isso depois precisa saber.

## 2026-09-26 — CORS: previews do Vercel por cima da base já existente

**Contexto:** o CORS base já tinha sido implementado no commit `ba2485d` (Pedro Costa):
`django-cors-headers` instalado, `CORS_ALLOWED_ORIGINS` via env var
`DJANGO_CORS_ALLOWED_ORIGINS` (default `localhost:3000,127.0.0.1:3000`) e `CORS_URLS_REGEX`
limitando a liberação a `^/api/.*$`. Esta sessão chegou a reimplementar o mesmo CORS em paralelo
sem saber; a versão duplicada foi descartada e apenas as duas lacunas foram somadas por cima:

- `CORS_ALLOWED_ORIGIN_REGEXES` com `^https://[a-zA-Z0-9-]+\.vercel\.app$` — os preview
  deployments do Vercel ganham um subdomínio novo a cada push, então nunca caberiam na lista fixa.
- `CSRF_TRUSTED_ORIGINS` — para o caso de algum fluxo passar a depender de cookies/sessão
  cross-origin (os endpoints `/api/v1/` atuais não dependem).

**Pendência:** setar `DJANGO_CORS_ALLOWED_ORIGINS` no ambiente de produção (Render) com o
domínio final do Vercel antes do deploy.

## 2026-09-26 — Dados de treino/inferência gerados (não são baixados pela API)

**Contexto:** a API de simulação (`web/studio/services/product.py`) só lê arquivos `.parquet`
estáticos do disco — nunca chama ONS/Open-Meteo/ARCO em tempo de requisição. Esses arquivos vivem
em `data/` e `outputs/`, ambos no `.gitignore`, então um `git clone` limpo não tem nenhum dado.

**O que foi gerado localmente** (rodando os scripts do pipeline, região **SE/CO** apenas):
- `data/processed/demand/load_hourly.parquet` — histórico ONS 2025 (`scripts/45_sync_ons_history.py`)
- `data/processed/generation/supply_by_subsystem_hourly.parquet` — idem
- `data/processed/climate/zone_climate_hourly_e3.parquet` — clima E2+E3 de 8 pontos representativos
  SE/CO (`scripts/31_download_e2_climate.py` → `32_prepare_e2_zone_climate.py` →
  `34_download_e3_context.py` → `35_prepare_e3_context.py`)
- `data/processed/tariff/base_tariffs.parquet` — tarifas ANEEL + mapa SIGEL (`scripts/44_prepare_tariff_geography.py`,
  100% local, sem internet)
- `outputs/metrics/e3_real_pilot_predictions.parquet` — janela replay 24h × 30 dias
  (`scripts/36_run_e3.py --subsystem "SE/CO" --test-hours 720 --calibration-hours 720`)

**Armadilha real encontrada:** o script `34_download_e3_context.py --target-year <ano>` pede o
ano **calendário inteiro** (`{ano}-01-01` a `{ano}-12-31`) à API de arquivo histórico do
Open-Meteo. Pedir o ano corrente (2026, ainda incompleto) devolve `HTTP 400`. Por isso a carga
(`load_hourly.parquet`) foi limitada a `--start-year 2025 --end-year 2025`: a janela de teste do
`36_run_e3.py` usa automaticamente as últimas N horas da carga, e ela precisa cair dentro do
período com clima enriquecido (`incident_*`/anomalias), que só existe para o ano calendário
completo mais recente (2025). Se um dia isso for regerado para incluir 2026 completo, repetir o
download de clima E3 também para 2026 depois que o ano terminar.

**Modelo treinado:** já existe no git (`models/demand/e3_seco_v1/` e `models/demand/*.json`) —
pesos Ridge reais, `MVP_FROZEN_AFTER_HELDOUT_SELECTION`. Não precisa retreinar para ter previsão;
precisa apenas dos dados acima para reconstruir as features de entrada.

**Só SE/CO está pronto.** N, NE e S não têm clima/predictions gerados ainda — repetir a mesma
sequência de scripts trocando `--subsystem`.

## 2026-09-26 — Endpoints REST para retreino/engenharia de features via frontend

**O que mudou:** `web/studio/api.py`, `web/studio/api_serializers.py` e `web/studio/api_urls.py`
ganharam 4 endpoints novos sob `/api/v1/`, expondo a infraestrutura de pipeline que já existia
(`stage_registry.py` + `PipelineRun` + `runner.launch_stage`, antes só acessível pela UI HTML em
`/pipeline/` e `/automacao/`):

| Método | Rota | Função |
|---|---|---|
| GET | `/api/v1/pipeline/stages/` | Lista as 22 etapas (dados, features, validação, treino, deployment) com seus parâmetros editáveis (`experiment`: E1/E2/E3, `algorithm`: ridge/xgboost, hiperparâmetros, janelas de data) e status atual (`READY`/`BLOCKED`/`DONE`). É o catálogo que o frontend usa para montar um formulário dinâmico de "engenharia de features". |
| POST | `/api/v1/pipeline/stages/<stage_id>/run/` | Dispara uma etapa assincronamente. Body: `{"params": {...}}` — qualquer param omitido cai no default do registry. Retorna `202` com o `run_id` imediatamente (a etapa roda em subprocesso separado, pode levar de segundos a horas). |
| GET | `/api/v1/pipeline/runs/<run_id>/` | Consulta status (`PENDING`/`RUNNING`/`SUCCESS`/`FAILED`), `return_code` e a cauda do log (`log_tail`, últimos 20k chars) de um run — inclusive runs disparados pela UI HTML antiga. |
| POST | `/api/v1/data/uploads/<dataset>/` | Upload multipart (`file`) que **sobrescreve diretamente** um dos arquivos processados canônicos. `dataset` ∈ `{load, supply, tariffs, climate_e3, predictions, signal}`. Aceita CSV, Parquet ou JSON (mesmo parser de `motor_sin.common.io.read_table`); converte e grava no formato Parquet esperado. |

**Fluxo pensado para o frontend:**
1. `GET /pipeline/stages/` para saber o que existe e quais parâmetros cada etapa aceita.
2. Opcional: `POST /data/uploads/<dataset>/` para injetar dados novos/customizados antes de
   retreinar.
3. `POST /pipeline/stages/validate_model/run/` (ou `train_model`, ou `full_automation`) com o
   body escolhendo `experiment`/`algorithm`/hiperparâmetros — é aqui que a "engenharia de
   features" acontece: trocar `experiment` entre E1 (histórico+calendário), E2 (+clima bruto) e
   E3 (+anomalias/eventos) muda literalmente o conjunto de features usado no treino.
4. Poll em `GET /pipeline/runs/<run_id>/` até `status` ser `SUCCESS`/`FAILED`.

**⚠️ Risco real, aceito deliberadamente para este MVP (decisão do usuário em 2026-09-26):**
- **Zero autenticação.** Qualquer chamador pode disparar `full_automation` (caro, pode levar
  horas) ou sobrescrever `load_hourly.parquet`/`base_tariffs.parquet`/etc. Confirmado na prática
  durante os testes desta mudança: um upload de teste com 2 linhas apagou o `load_hourly.parquet`
  real de 2025 que tinha sido gerado a peso de vários scripts — foi preciso rodar
  `45_sync_ons_history.py` de novo para restaurar.
- **`DataUploadApi` não valida schema.** Aceita qualquer CSV/Parquet parseável e sobrescreve o
  arquivo canônico sem checar colunas, tipos ou continuidade horária. Um upload malformado só vai
  quebrar mais tarde, na hora de simular ou treinar, com um erro `400` genérico do
  `simulate_customer`/`fit_direct_models`.
- **`StageRunApi` não tem rate limit nem fila.** Nada impede disparar a mesma etapa pesada
  (`full_automation`) várias vezes em paralelo e saturar CPU/rede do servidor.
- Antes de expor isso a usuários reais (não só ao time), adicionar no mínimo: autenticação por
  API key, validação de schema no upload (comparar colunas esperadas por dataset), e um lock que
  impeça duas execuções concorrentes da mesma stage.

**Documentação viva:** os 4 endpoints novos aparecem automaticamente em `/api/docs/` (Swagger) e
`/api/schema/` (OpenAPI), nas tags `Pipeline` e `Dados` (`SPECTACULAR_SETTINGS` em `settings.py`).

## 2026-09-26 — Semear dados no Render sem acesso ao build (via upload pela API)

**Problema:** o deploy no Render builda a partir do git, e `data/`/`outputs/` estão no
`.gitignore` — então o backend sobe **sem nenhum parquet** e toda simulação falha com 400. O
dono do projeto não tem acesso ao build/shell do Render, então rodar o pipeline lá ou commitar
os arquivos não eram opções viáveis.

**Solução adotada:** usar o próprio `DataUploadApi` para empurrar os 5 parquets gerados
localmente para a instância remota. Para isso `UPLOAD_DATASET_PATHS` (`web/studio/api.py`) ganhou
duas entradas que faltavam:
- `predictions` → `outputs/metrics/e3_real_pilot_predictions.parquet` — **sem este o modo
  `replay` falha** com "Não há janela histórica completa de 24h"; era o furo que inviabilizava
  semear o servidor só por upload.
- `signal` → `outputs/contracts/system_signal_v1.parquet` — para o modo `operational`, quando
  existir.

Ordem de upload (5 chamadas, ~5,4 MB no total), validada ponta a ponta localmente: `load`,
`supply`, `tariffs`, `climate_e3`, `predictions`. Depois disso
`POST /api/v1/simulations/` volta a responder 200.

**⚠️ Disco efêmero:** no plano padrão do Render o filesystem **não persiste** entre deploys e
reinícios. Os arquivos enviados por upload somem a cada redeploy/restart do serviço, e a sequência
de 5 uploads precisa ser repetida. Solução definitiva seria um Persistent Disk no Render (ou
mover esses artefatos para um bucket S3/GCS lido no startup) — fora de escopo enquanto for MVP.

**⚠️ Atenção ao testar/usar `StageRunApi`:** a etapa `bootstrap_contracts`
(`scripts/00_bootstrap_phase0.py --require-parquet`) regrava
`contracts/fixtures/system_signal_v1_example.parquet` e `contracts/fixtures/tariff_v1_example.parquet`
— e esses dois arquivos **estão versionados no git** (diferente de tudo em `data/`/`outputs/`). O
conteúdo regravado é idêntico em dados (confirmado comparando dataframes), só a codificação
binária do parquet muda, mas isso ainda aparece como "modificado" no `git status`. Rodar essa
stage (via API ou UI) e depois esquecer de checar `git status` pode levar a um commit acidental
de um diff binário sem mudança real. Sempre correr `git checkout -- contracts/fixtures/*.parquet`
depois de testar essa stage, a menos que a intenção seja mesmo atualizar os fixtures.
