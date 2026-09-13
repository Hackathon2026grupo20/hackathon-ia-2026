# Datasets complementares — Rio de Janeiro

Mapeamento de fontes que podem complementar **carga histórica + clima + calendário** na previsão de demanda do estado do Rio de Janeiro (issue #3).

Nesta etapa sobe apenas o mapeamento, sem arquivos brutos.

## Premissas do recorte

- **Região:** estado do Rio de Janeiro. No ONS, corresponde à área de carga `RJ` (subsistema Sudeste/Centro-Oeste).
- **Variável alvo de referência:** carga verificada da área `RJ` (ONS), em MWmed, semi-horária.
- Fontes disponíveis só por subsistema (SE/CO) ou submercado são menos úteis porque misturam RJ com SP, MG, ES e Centro-Oeste.

## Legenda de prioridade

- **MVP** — hipótese forte e integração simples; testar agora.
- **Importante** — pode agregar, mas exige esforço adicional; testar se houver tempo.
- **Nice to have** — interessante, mas não necessário para validar a hipótese principal.
- **Descartar** — baixo benefício, integração difícil ou granularidade incompatível.

---

## 1. Sistema elétrico, geração e indicadores energéticos (Pedro)

| Nome / fonte | Link | Variável disponível | Cobertura temporal | Granularidade temporal | Granularidade geográfica | Hipótese de como ajudaria a previsão | Facilidade de integração | Limitações | Tag / prioridade |
|---|---|---|---|---|---|---|---|---|---|
| ONS — Carga Verificada (parcela MMGD) | [dados.ons.org.br](https://dados.ons.org.br/dataset/carga-energia-verificada) · API `apicarga.ons.org.br/prd/cargaverificada` | `val_cargammgd` (carga atendida por micro e minigeração distribuída), `val_cargaglobalsmmgd` (carga líquida de MMGD), `val_cargasupervisionada`, `val_carganaosupervisionada` | Carga da área RJ na API desde 2016 (vazia em jan/2015); parcela MMGD preenchida a partir de 2020 (vazia em 2019) | Semi-horária (30 min) | Área de carga `RJ` | Separa o efeito da geração solar distribuída, que reduz a carga vista pela rede ao meio-dia. Permite modelar carga global e carga líquida separadamente e explicar a queda no meio do dia em dias ensolarados | Muito alta: mesma API, mesma chave (`cod_areacarga` + `din_referenciautc`) da variável alvo | MMGD é **estimada** pelo ONS, não medida; histórico curto; valores revisados por processos de consistência; timestamps em UTC | **MVP** |
| ANEEL — Relação de empreendimentos de Mini e Microgeração Distribuída | [dadosabertos.aneel.gov.br](https://dadosabertos.aneel.gov.br/dataset/relacao-de-empreendimentos-de-geracao-distribuida) | Data de conexão, fonte (solar, eólica etc.), potência instalada (kW), distribuidora, município, UF | Dez/2008 em diante; atualização diária | Evento (data de conexão) → agregável em potência acumulada diária ou mensal | Município / UF / distribuidora (Light, Enel Rio) | A potência solar instalada acumulada no RJ explica a tendência de queda da carga líquida e, combinada com irradiação (clima), estima quanto a GD "esconde" da demanda. Também ajuda a projetar a MMGD quando o dado do ONS não cobre o período | Alta: CSV/Parquet sem cadastro; filtrar `UF = RJ`, agregar por data | É capacidade instalada, não geração; migração do SISGD para o novo sistema MMGD (set–nov/2025) atrasou registros; arquivo nacional grande | **MVP** |
| ONS — Carga Programada | [dados.ons.org.br](https://dados.ons.org.br/dataset/carga-energia-programada) · API `apicarga.ons.org.br/prd/cargaprogramada` | `val_cargaglobalprogramada` (previsão oficial do ONS) | Área RJ na API a partir de 2021 (vazia em jan/2021, presente em jul/2021) | Semi-horária (30 min) | Área de carga `RJ` | Serve de **baseline oficial**: o modelo precisa superar a previsão do próprio ONS para mostrar valor. Também dá para usar como feature, se o horizonte for compatível | Muito alta: mesma API e chaves da carga verificada | É previsão, não explica causas; se usada como feature, cuidado com vazamento de informação conforme o horizonte | **MVP** (baseline de comparação) |
| ONS — Geração por Usina em Base Horária | [dados.ons.org.br](https://dados.ons.org.br/dataset/geracao-usina-2) | `val_geracao` por usina, com `id_estado`, tipo de usina, combustível e modalidade — inclui linhas agregadas "Pequenas Usinas (MMGD)" por estado | 2000 em diante; atualização diária | Horária | Usina / estado (`id_estado = RJ`) / subsistema | A linha de MMGD fotovoltaica do RJ dá um sinal horário de geração distribuída que pode validar a parcela MMGD da carga. A geração térmica e nuclear (Angra) descreve a oferta, não a demanda | Média: arquivos mensais grandes (download lento); filtrar estado e tipo | Geração centralizada explica oferta, não consumo; risco de feature sem relação causal com a demanda | **Importante** (só a parte MMGD) |
| CCEE — Consumo Horário por Perfil de Agente | [dadosabertos.ccee.org.br](https://dadosabertos.ccee.org.br/dataset/consumo_horario_perfil_agente) | Consumo bruto e ajustado por agente, ativo de carga, ramo de atividade e distribuidora | Mar/2024 a jul/2026 | Horária (arquivos mensais) | Agente / distribuidora (não confirmado se há UF) | Consumo de grandes consumidores (mercado livre) por ramo de atividade em Light/Enel Rio pode explicar variações industriais e comerciais que clima e calendário não captam | Baixa a média: arquivos GZIP grandes, exige mapear agentes e distribuidoras ao RJ | Histórico curto (~2 anos); cobre só agentes da CCEE, não o consumidor cativo; publicação mensal com defasagem | **Importante** |
| ANEEL — SAMP (mercado das distribuidoras) | [dadosabertos.aneel.gov.br](https://dadosabertos.aneel.gov.br/dataset/samp) | Energia e consumidores por classe de consumo (residencial, comercial, industrial etc.) por distribuidora | 2003 em diante; atualização mensal | Mensal | Distribuidora (a confirmar Light e Enel Distribuição Rio) | Mudanças na composição do consumo por classe explicam tendências estruturais da carga do RJ | Média: agregação mensal, precisa desagregar para a frequência do modelo | Frequência mensal não explica picos diários ou horários; distribuidora não coincide exatamente com o estado | **Nice to have** |
| ONS — Curva de Carga Horária | [dados.ons.org.br](https://dados.ons.org.br/dataset/curva-carga) | `val_cargaenergiahomwmed` | 2000 em diante | Horária | Apenas subsistema (N, NE, S, SE) | Contexto do subsistema SE/CO, que também atende o RJ | Alta | Não tem recorte RJ; a carga verificada por área de carga é mais adequada | **Descartar** |
| ONS — Fator de Capacidade Eólica e Solar | [dados.ons.org.br](https://dados.ons.org.br/dataset/fator-capacidade-2) | Geração programada e verificada, capacidade instalada, fator de capacidade, coordenadas | 2009 em diante | Horária | Usina / conjunto, com estado | Proxy de irradiação e vento | Média | Cobre só usinas centralizadas despachadas pelo ONS; o arquivo de jan/2025 não tem nenhuma usina no RJ. Irradiação já vem das fontes climáticas | **Descartar** |
| ONS — Balanço de Energia e Intercâmbios entre subsistemas | [dados.ons.org.br](https://dados.ons.org.br/) | Geração, carga e intercâmbio por subsistema | Vários anos | Horária / diária | Subsistema | Contexto de operação do SIN | Média | Descreve oferta e transmissão, não demanda do RJ; granularidade geográfica incompatível | **Descartar** |
| ONS — Restrição por Constrained-off | [dados.ons.org.br](https://dados.ons.org.br/) | Cortes de geração eólica e solar | Recente | Semi-horária / horária | Usina / conjunto | Nenhuma relação direta com a demanda | Média | Fenômeno de oferta, concentrado no Nordeste | **Descartar** |
| CCEE — PLD Horário | [dadosabertos.ccee.org.br](https://dadosabertos.ccee.org.br/dataset/pld_horario) | Preço de Liquidação das Diferenças | Semanal 2001–2020; horário 2021+ | Horária | Submercado (SE/CO) | Sinal de preço poderia afetar consumidores do mercado livre | Alta (CSV) | Consumidor cativo não responde ao PLD no curto prazo; submercado inteiro, não RJ | **Descartar** |
| ANEEL — Bandeiras Tarifárias | [dadosabertos.aneel.gov.br](https://dadosabertos.aneel.gov.br/dataset/bandeiras-tarifarias) | Bandeira vigente (verde, amarela, vermelha) | A confirmar | Mensal | Nacional | Tarifa mais cara poderia reduzir consumo residencial | Alta | Frequência mensal e mesma bandeira para todo o país; efeito pequeno e difícil de isolar | **Descartar** |

---

## 2. Socioeconômico, consumo por setor, calendário e mobilidade (Rômulo)

_A preencher, seguindo o mesmo formato de tabela._

---

## 3. Seleção para teste

Escolha de no máximo 3 fontes na parte de sistema elétrico:

1. **ONS — Carga Verificada, parcela MMGD (RJ):** mesma fonte e chave da variável alvo, custo de integração quase zero e hipótese clara sobre a curva do meio do dia.
2. **ANEEL — Geração distribuída (RJ):** explica a tendência estrutural da carga líquida e complementa o histórico curto de MMGD do ONS.
3. **ONS — Carga Programada (RJ):** não é feature explicativa, mas é o baseline oficial contra o qual o modelo deve ser comparado.

## 4. O que não vale o esforço agora

- Bases disponíveis **só por subsistema ou submercado** (curva de carga horária, balanço, intercâmbios, PLD): não isolam o RJ.
- Bases que descrevem **oferta** e não demanda (geração centralizada, constrained-off, fator de capacidade).
- Sinais **mensais e nacionais** (bandeiras tarifárias).

## 5. Pendências

- Confirmar o mês exato de início da área `RJ` na API do ONS (verificada: entre jan/2015 e jan/2016; programada: entre jan/2021 e jul/2021). Valores de 2010 vêm zerados.
- Confirmar se o SAMP e o consumo horário da CCEE permitem isolar Light e Enel Distribuição Rio.
- Validar com dados reais se as fontes MVP melhoram as métricas definidas no issue #1.
