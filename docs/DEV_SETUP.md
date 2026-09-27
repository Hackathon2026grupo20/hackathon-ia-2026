# Ambiente de desenvolvimento

Como subir a API e o Studio em uma máquina nova, a partir de um `git clone`, sem precisar
refazer o pipeline de ETL.

## Por que esta branch existe

`data/` e `outputs/` são ignorados pelo git, então um clone limpo não tem nenhum dado e toda
simulação falha com `400`. Levantar esses dados do zero exige baixar histórico da ONS, clima
multi-ano do Open-Meteo e rodar validação de modelo — algo entre dezenas de minutos e algumas
horas, com dependência de APIs externas.

Para encurtar isso, o `.gitignore` abre exceção para **cinco** arquivos: o seed mínimo que faz a
região **SE/CO** funcionar de ponta a ponta.

| Arquivo | Conteúdo | Gerado por |
|---|---|---|
| `data/processed/demand/load_hourly.parquet` | carga horária ONS, 2025, 5 subsistemas | `scripts/45_sync_ons_history.py` |
| `data/processed/generation/supply_by_subsystem_hourly.parquet` | geração/intercâmbio por subsistema | idem |
| `data/processed/climate/zone_climate_hourly_e3.parquet` | clima E2+E3 (anomalias/eventos), SE/CO | `scripts/31→32→34→35` |
| `data/processed/tariff/base_tariffs.parquet` | tarifas ANEEL homologadas + join com SIGEL | `scripts/44_prepare_tariff_geography.py` |
| `outputs/metrics/e3_real_pilot_predictions.parquet` | 30 janelas de replay de 24h (dez/2025) | `scripts/36_run_e3.py` |

O GeoJSON das áreas de concessão e o catálogo de distribuidoras não entram na lista porque já
existem versionados em `configs/`, de onde `services/distribution.py` os lê como fallback.

## Subindo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Verificação rápida — deve responder `"simulation_available": true`:

```bash
curl -s "http://127.0.0.1:8000/api/v1/simulations/options/?region=SE/CO"
```

E a simulação completa:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/simulations/ \
  -H "Content-Type: application/json" \
  -d '{"cnpj":"33050071000158","region":"SE/CO","distributor":"ENEL RJ",
       "profile":"B1|Convencional|Residencial|Residencial|Tarifa de Aplicação",
       "monthly_kwh":350,"customer_type":"residential","mode":"replay","flexible_pct":20}'
```

O Studio fica em `http://127.0.0.1:8000/` e a documentação da API em `/api/docs/`.

## Frontend em outra origem

O CORS já libera `localhost:3000` e `127.0.0.1:3000` para as rotas `/api/*`. Para outros
domínios, use a variável de ambiente (ela **substitui** o default, então inclua o localhost se
ainda precisar dele em dev):

```bash
DJANGO_CORS_ALLOWED_ORIGINS=https://seu-app.vercel.app,http://localhost:3000
```

## O que o seed NÃO cobre

- **Só a região SE/CO.** `N`, `NE` e `S` respondem `simulation_available: false`. Para habilitá-las,
  repita as etapas de clima e validação trocando o subsistema (pela UI em `/pipeline/` ou pelos
  scripts).
- **Só o modo `replay`.** O modo `operational` precisa de `outputs/contracts/system_signal_v1.parquet`,
  que depende de um forecast com issue time recente — rode a etapa "Construir system_signal_v1".
  Em `replay`, sem `replay_key` no request, a API usa a janela mais recente: **31/12/2025**.
- **A curva de consumo do cliente é sintética.** É um perfil fixo por tipo de consumidor
  (`motor_tarifa/customer/profiles.py`), não medição real. A previsão de demanda do sistema, essa
  sim, vem do modelo treinado.

## Regerando os dados

Pela interface, em `/pipeline/`, nesta ordem (cada etapa desbloqueia a seguinte):

1. Adicionar/consolidar anos ONS — `2021` a `2025`
2. Carregar mapa + tarifas ANEEL
3. Baixar clima E2 — `SE/CO`
4. Preparar E2 — `SE/CO`
5. Baixar baseline E3 — `SE/CO`, `2025`
6. Construir E3 — `SE/CO`, `2025`
7. Reproduzir E0–E3 Ridge — `720`/`720`

### Armadilha: o ano tem que ser 2025

`scripts/34_download_e3_context.py --target-year <ano>` pede o **ano calendário inteiro**
(`{ano}-01-01` a `{ano}-12-31`) à API de arquivo do Open-Meteo. Pedir o ano corrente, ainda
incompleto, devolve `HTTP 400`.

A consequência é menos óbvia: `36_run_e3.py` usa automaticamente as **últimas N horas da carga**
como janela de teste, e essa janela precisa cair dentro do período com clima enriquecido
(colunas `incident_*`). Se a carga for sincronizada até 2026 mas o clima E3 só existir para 2025,
o script falha com `no complete fixed forecast origins after target/exogenous availability checks`.
Por isso a carga do seed vai só até 2025.

## Modelos

Não é preciso treinar: os pesos Ridge congelados já estão versionados em `models/demand/`
(`e3_seco_v1/`, status `MVP_FROZEN_AFTER_HELDOUT_SELECTION`). O pipeline acima só reconstrói os
dados de entrada que alimentam esses modelos.
