# Analisi costi — Limen su AWS, Azure o Google Cloud

> Redatta il 2026-10-11 per valutare i programmi di crediti cloud per progetti
> open source. Prezzi di listino **on-demand in USD**, mese = 730 h, regioni
> italiane dove esistono (AWS `eu-south-1` Milano, Azure Italy North, GCP
> `europe-west8` Milano). **(stima)** = cifra non confermata su una pagina
> ufficiale per quella regione. I listini cambiano: ricontrollare prima di
> allegare questi numeri a una domanda.

⚠️ **Prerequisito di governance.** `CLAUDE.md` e la memoria `deploy-target`
fissano «self-hosted VPS + Docker, no cloud providers». Una migrazione richiede
di rivedere esplicitamente quell'invariante, non di aggirarlo.

---

## 1. Footprint misurato (server attuale, 2026-10-11)

| Risorsa | Valore |
|---|---|
| CPU | worker a ~1 core saturo durante lo sweep; il resto quasi idle |
| RAM in uso | ~10 GB (Postgres 6,3 · GeoServer 1,6 · Open-Meteo 0,9 · worker 0,7 · MCP 0,4) |
| DB `limen` | 39 GB (+ `gis` di GeoServer 4,5 GB) |
| Dati statici (DTM 5 m, CORINE, carta geolitologica) | ~47 GB |
| Volume Open-Meteo self-hosted | 8,6 GB |
| Modelli locali (`/srv/models`) | 423 GB — quasi tutto GLM-5.2 (colibrì); GGUF piccoli su Quadro RTX 4000 8 GB |
| Gateway LiteLLM | ruoli `fast`/`chat`/`extract` (4–8B) ed `embed` in locale; `fast-cloud` = Claude Haiku 5.5, `quality-cloud` = Claude Sonnet 5.5; tetto di spesa 50 $/30 giorni |

Dimensionamento risultante: **8 vCPU / 32 GB, ~300 GB SSD** per lo stack
completo; con Postgres gestito bastano **4 vCPU / 16 GB** per l'applicazione e
un DB **4 vCPU / 16 GB, 200 GB**.

---

## 2. Prezzi unitari di riferimento

### Calcolo e storage

| | AWS Milano | Azure Italy North | GCP Milano |
|---|---|---|---|
| VM 8 vCPU / 32 GB | m6i.2xlarge 327 $ | D8s_v5 327 $ | n2-standard-8 329 $ (≈263 $ con sustained-use) |
| VM 16 vCPU / 64 GB | 654 $ | 654 $ | 658 $ (≈526 $) |
| SSD a blocchi, $/GB-mese | gp3 0,092 | Premium SSD v2 0,093 | pd-balanced 0,116 |
| Object storage, $/GB-mese | S3 0,024 | Blob Hot LRS 0,019 | GCS 0,023 |
| Egress Internet, primo TB | 0,09 $/GB | 0,087 $/GB (100 GB gratis) | 0,12 $/GB (stima) |

### Postgres gestito (PG16)

| | 4 vCPU / 16 GB | 4 vCPU / 32 GB | Storage $/GB-mese | HA |
|---|---|---|---|---|
| **RDS** Milano | db.m6i.xlarge 302 $ | db.r6i.xlarge 429 $ | 0,133 | Multi-AZ ≈ ×2 (604 $ + 0,266/GB) |
| **Azure Flexible Server** Italy North | D4ds_v5 310 $ | E4ds_v5 441 $ | 0,137 | zone-redundant ≈ ×2 |
| **Cloud SQL Enterprise** Milano | ≈234 $ (stima, da Iowa +16 %) | ≈330 $ (stima) | ≈0,20 (stima) | HA ≈ ×2 |

Estensioni: PostGIS, pgvector e pg_cron sono disponibili su tutti e tre.
Azure richiede l'allowlist in `azure.extensions`; pg_cron vuole
`shared_preload_libraries` (RDS, Azure) o il flag `cloudsql.enable_pg_cron`
(Cloud SQL). Il fallback APScheduler resta comunque valido.

### Inferenza gestita

**Claude (stesso modello del gateway attuale)**

| Canale | Haiku 5.5 | Sonnet 5.5 | Residenza UE | Sovrapprezzo UE |
|---|---|---|---|---|
| API Anthropic diretta (oggi) | 0,10 / 0,50 $/MTok (≤100k token di prompt) | 2 / 10 $/MTok | no (`global` o `us`) | — |
| AWS Bedrock | listino (stima) | 2 / 10 (stima) | **sì**, profili `eu.anthropic.*` (Francoforte, Milano, Parigi…) | +10 % sugli endpoint regionali |
| Google Vertex AI | listino | listino | **sì**, multi-region `eu` | +10 % |
| Microsoft Foundry | listino (in CCU) | listino | **no** (Global o US Data Zone) | — |

**Modelli open-weight a consumo (sostituti dei 4–8B locali)**

| Piattaforma | Modello | $/MTok in / out |
|---|---|---|
| Bedrock | gpt-oss-20b | 0,07 / 0,30 (stima) |
| Bedrock | Ministral 8B | 0,15 / 0,15 |
| Vertex MaaS | gpt-oss-20b | 0,075 / 0,30 (stima) |
| Foundry | Mistral Small | 0,10 / 0,30 (stima) |
| Foundry | gpt-oss-120b | 0,15 / 0,60 (stima) |

**Embedding:** Titan v2 0,02 $/MTok (stima) · Azure `text-embedding-3-small`
0,02 (0,022 Data Zone UE) · Vertex `gemini-embedding-001` 0,15 (stima).

**GPU per ospitare i modelli piccoli in proprio**

| VM | GPU | $/h | $/mese | spot $/h |
|---|---|---|---|---|
| AWS g4dn.xlarge (Francoforte) | T4 16 GB | 0,658 | ~480 | 0,317 |
| AWS g6.xlarge (Francoforte) | L4 24 GB | 1,006 | ~735 | 0,476 |
| Azure NC4as_T4_v3 (UE) | T4 16 GB | 0,56–0,66 | ~407–480 | — |
| GCP g2-standard-4 (europe-west4) | L4 24 GB | 0,743 (stima) | ~542 | 0,371 (stima) |

GLM-5.2 (400 GB) non è trasferibile a un costo sensato: richiederebbe
un'istanza multi-GPU da migliaia di $/mese. In cloud il ruolo `quality-*` va
su Sonnet 5.5, come già fa `quality-cloud`.

---

## 3. Scenari

Ipotesi comuni: ~200 GB/mese di egress (traffico mappa reale **non misurato**),
~100 GB di object storage/backup.

### A — Lift & shift (una VM, compose invariato)

Postgres, GeoServer, Open-Meteo e app restano container sulla stessa VM;
l'inferenza resta com'è oggi (Claude via API diretta; i modelli locali
spariscono o vanno su API a consumo, vedi D).

| | AWS | Azure | GCP |
|---|---|---|---|
| VM 8/32 | 327 | 327 | 263 |
| 300 GB SSD | 28 | 28 | 35 |
| Object storage + egress | 11 | 11 | 26 |
| **Totale mese / anno** | **~366 $ / 4,4 k$** | **~366 $ / 4,4 k$** | **~324 $ / 3,9 k$** |

Cambiano solo `.env` e `LIMEN_PGDATA_DIR`. Su Azure l'`ObjectStore` usa il
backend `filesystem` (Blob non è S3-compatibile e il codice supporta solo
filesystem o S3). Risolve anche il problema del disco `sdb` degradato.

### B — Postgres gestito al posto del container

VM 4/16 per API, worker, GeoServer, pg_tileserv, Open-Meteo, MCP; DB gestito
4 vCPU/16 GB con 200 GB (ospita anche il DB `gis`).

| | AWS (RDS) | Azure (Flexible) | GCP (Cloud SQL) |
|---|---|---|---|
| VM 4/16 + 150 GB | 178 | 178 | 148 |
| DB gestito + 200 GB | 329 | 337 | 273 (stima) |
| Object storage + egress | 11 | 11 | 26 |
| **Totale mese / anno** | **~518 $ / 6,2 k$** | **~526 $ / 6,3 k$** | **~447 $ / 5,4 k$** |
| con DB in HA | ~850 $ | ~860 $ | ~700 $ (stima) |

Cosa si guadagna: backup automatici, PITR, patching, HA opzionale.
Cosa si perde: controllo su `shared_preload_libraries`/estensioni, tuning
del filesystem, e la portabilità — finiti i crediti si resta legati al
provider o si rifà la migrazione del DB.

### C — Cloud-native: DB gestito + inferenza gestita

Scenario B più il gateway LiteLLM (che resta sulla VM: l'invariante «un solo
endpoint di inferenza» non cambia) instradato verso i servizi del provider.
Il codice Limen non cambia: cambia il `model_list` di `/etc/litellm/config.yaml`.

**Il costo dell'inferenza dipende dal volume di token, che non è misurato.**
Il dato documentato è Claude Haiku a ~1–3 $/mese per i briefing; il tetto
del gateway è 50 $/30 giorni. Per un volume plausibile di 5–20 MTok/mese:

| Opzione per i ruoli `fast`/`chat`/`extract`/`embed` | Costo mese |
|---|---|
| **C1 — API a consumo** (Haiku 5.5, gpt-oss-20b, Mistral Small, embedding) | **~2–15 $** |
| **C2 — VM GPU con llama.cpp/llama-swap** (come oggi, in cloud) | **~410–540 $** |

Punto di pareggio: una T4 a ~480 $/mese equivale a ~2–3 **miliardi** di token
al mese a 0,10–0,20 $/MTok. Limen è tre ordini di grandezza sotto: **la GPU
dedicata non conviene**.

| Totale C1 (B + inferenza a consumo) | AWS | Azure | GCP |
|---|---|---|---|
| Mese | ~530 $ | ~540 $ | ~460 $ |
| Anno | ~6,4 k$ | ~6,5 k$ | ~5,5 k$ |

| Totale C2 (B + VM GPU) | AWS | Azure | GCP |
|---|---|---|---|
| Mese | ~1.000 $ | ~945 $ | ~990 $ |
| Anno | ~12 k$ | ~11,3 k$ | ~11,9 k$ |

Residenza dei dati:
- **Bedrock `eu.*`** e **Vertex `eu`** sono gli unici canali con Claude in UE
  (+10 % sul listino). Oggi l'API diretta gira in `global`, quindi passare a
  uno dei due è un miglioramento, non un requisito.
- **Foundry non ha Claude in UE.** Su Azure, per restare in UE, i ruoli brevi
  vanno su modelli venduti direttamente da Azure (gpt-oss, Mistral, Azure
  OpenAI) e Claude resta globale.

---

## 4. Cosa coprono davvero i crediti

**I crediti non pagano Claude su nessuno dei tre cloud.** Claude su Bedrock e
su Foundry è fatturato tramite Marketplace, escluso sia dai promotional
credits AWS (Open Source Credits compresi) sia dal grant nonprofit Azure
(«applies only to first-party Microsoft Azure services»); su Vertex è un
partner model escluso dai crediti trial e startup. Fa eccezione, secondo
fonti non ufficiali, AWS Activate per le startup.

I crediti coprono: VM (anche GPU), dischi, storage, egress, DB gestiti e i
modelli **first-party** (Titan, gpt-oss/Mistral venduti da AWS o Azure,
Azure OpenAI, Gemini).

### Programmi

| Programma | Credito | Serve | Stato 2026 |
|---|---|---|---|
| **AWS Open Source Credits** | non pubblicato, 1 anno, si richiede ogni anno | licenza OSI; nessun ente. Favoriti fondazioni e progetti multi-organizzazione | attivo |
| AWS Cloud Credit for Research | su misura, 1 anno | docente/studente di un ateneo | attivo |
| AWS Activate Founders | 1–5 k$ una tantum | società < 10 anni | attivo |
| AWS Imagine Grant | fino a ~100 k$ | charity US/UK/IE/CA/AU/NZ | **Italia esclusa** |
| Google Cloud Research Credits | ~5 k$ (docente), ~1 k$ (dottorando) | ateneo o ente di ricerca | attivo (Italia da verificare) |
| Google for Startups Cloud | ~2–5 k$ (Start, stima) fino a 200–350 k$ | società; tier alti con VC | attivo |
| Google.org Impact Challenge (clima) | 0,5–3 M$ + crediti | nonprofit o ente accademico | bandi periodici |
| **Azure for Nonprofits** | **2.000 $/anno, rinnovabile** | ETS validato; no riservate, no Marketplace | attivo |
| Microsoft for Startups | 1 k$ → 5 k$ (fino a 150 k$ con investitori) | società | attivo |
| Azure open source credits | — | — | **form chiuso** |
| EOSC EU Node | VM gratuite fino a 64 vCPU / 128 GB, GPU | affiliazione accademica UE | attivo |
| OVHcloud / Scaleway startup | 10 k€ / fino a 36 k€ | società UE | attivi |

### Copertura per scenario (costo annuo a listino)

| Scenario | Anno | Azure nonprofit (2 k$) | Ricerca Google (~5 k$) | Startup (~5 k$) |
|---|---|---|---|---|
| A — lift & shift | 3,9–4,4 k$ | ~45–50 % | ~1 anno | ~1 anno, una volta |
| B — Postgres gestito | 5,4–6,3 k$ | ~32–37 % | ~10 mesi | ~10 mesi |
| C1 — gestito + inferenza a consumo | 5,5–6,5 k$ (Claude escluso dai crediti) | ~31 % | ~10 mesi | ~10 mesi |
| C2 — gestito + GPU | 11–12 k$ | ~17 % | ~5 mesi | ~5 mesi |

---

## 5. Raccomandazioni

1. **Se si migra, scenario A.** È il più economico, l'unico interamente
   coperto da crediti modesti, e lascia il compose identico: alla scadenza
   dei crediti si torna su VPS senza riscrivere nulla.
2. **Inferenza: API a consumo, mai GPU dedicata.** Instradare i ruoli
   `fast`/`chat`/`extract`/`embed` del gateway verso modelli first-party a
   consumo (gpt-oss, Mistral, Titan/Azure embedding) costa pochi dollari al
   mese ed è pagabile coi crediti; Claude resta una voce a parte, su carta.
   Per avere Claude in UE: Bedrock `eu.*` o Vertex `eu`.
3. **Postgres gestito solo se serve HA** e c'è un budget oltre i crediti:
   costa +40–60 % rispetto ad A e lega al provider.
4. **Fare domanda subito ad AWS Open Source Credits** (non serve un ente;
   base: `docs/OSS_IMPACT.md`). Il maintainer unico è il punto debole: una
   co-firma accademica lo attenua.
5. **Cercare un partner accademico** (es. CNR-IRPI, UniBas): apre i crediti
   di ricerca AWS/Google, EOSC e i bandi Google.org, che hanno la miglior
   aderenza tematica.
6. **Costituire un ETS** solo se serve anche per altro: aggiunge 2 k$/anno
   rinnovabili su Azure e l'accesso ai bandi nonprofit.

### Dati mancanti

- Costo attuale (server dedicato + VPS Aruba), per la colonna «oggi».
- Volume di token mensile per ruolo: va letto dai log `llm.usage` o dalla
  spesa del gateway LiteLLM, e sostituito alla forchetta 5–20 MTok.
- Egress reale della mappa pubblica (log del reverse proxy).

---

## Fonti

- AWS EC2 Milano: <https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/EU%20(Milan)/Linux/index.json>
- AWS RDS Milano: <https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/eu-south-1/index.csv>
- AWS EBS / S3 / data transfer: <https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ebs.json>, <https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/s3/USD/current/s3.json>, <https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/datatransfer/USD/current/datatransfer.json>
- Azure Retail Prices API: <https://prices.azure.com/api/retail/prices>
- GCP: <https://gcloud-compute.com/europe-west8.html>, <https://cloud.google.com/sql/pricing>, <https://cloud.google.com/storage/pricing>
- Estensioni: <https://learn.microsoft.com/azure/postgresql/extensions/concepts-extensions-by-engine>, <https://docs.cloud.google.com/sql/docs/postgres/extensions>
- Claude: <https://platform.claude.com/docs/en/about-claude/pricing>, <https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html>, <https://platform.claude.com/docs/en/build-with-claude/claude-on-vertex-ai>, <https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry>
- Bedrock: <https://aws.amazon.com/bedrock/pricing/>
- GPU: <https://www.azurespeed.com/AzureVmPricing/Standard_NC4as_T4_v3>, <https://www.doit.com/compute/spot/eu-central-1/g4dn.xlarge>, <https://www.devzero.io/instances/gcp/g2-standard-4>
- Crediti: <https://aws.amazon.com/blogs/opensource/aws-promotional-credits-open-source-projects/>, <https://aws.amazon.com/awscredits/>, <https://learn.microsoft.com/industry/nonprofit/microsoft-for-nonprofits/claim-activate-nonprofit-azure-grant>, <https://learn.microsoft.com/en-us/startups/benefits/technical-benefits/azure-credits/foundry-model-sponsorship-coverage>, <https://opensource.microsoft.com/azure-credits>, <https://edu.google.com/programs/credits/research/>, <https://open-science-cloud.ec.europa.eu/about/access-policy>
