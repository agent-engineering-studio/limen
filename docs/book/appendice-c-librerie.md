# Appendice C. Indice delle librerie

Questa appendice elenca i pezzi di programma su cui Limen è costruito: prima
le undici librerie nate dentro Limen, poi gli strumenti liberi costruiti da
altri. Per ognuno: la **versione minima** che Limen richiede, la
**licenza** (le regole con cui si può usare), a cosa serve e dove trovarlo.
Il racconto di ciascuna è nel [capitolo 2](02-le-librerie.md).

Una nota sulle licenze, per chi non le frequenta. **Apache-2.0**, **MIT** e
**BSD** sono licenze «permissive»: si può usare, modificare e rivendere il
programma, purché si citi chi l'ha scritto. **EUPL-1.2**, la licenza di Limen,
è la licenza aperta dell'Unione Europea: chi distribuisce una versione
modificata deve renderla aperta a sua volta.

*Versioni e licenze controllate l'8 novembre 2026 sul file delle dipendenze
di Limen e sui registri pubblici dei pacchetti; tutti i link rispondevano in
quella data.*

## Le librerie nate da Limen

Tutte con licenza Apache-2.0, pubblicate dall'organizzazione
`agent-engineering-studio`. Il segno `~=` vuol dire «questa versione, con i
soli aggiornamenti di correzione»: un cambiamento più grande arriva in Limen
solo per scelta.

| Libreria | Versione | A cosa serve in Limen | Link |
|---|---|---|---|
| fwi-chain | ~= 1.0.0 | calcola l'indice meteo degli incendi, giorno dopo giorno | [documentazione](https://agentengineering.it/fwi-chain/) · [GitHub](https://github.com/agent-engineering-studio/fwi-chain) |
| effis-client | ~= 0.1.2 | scarica le aree bruciate in Europa e le mappe ufficiali dell'indice degli incendi | [documentazione](https://agentengineering.it/effis-client/) · [GitHub](https://github.com/agent-engineering-studio/effis-client) |
| rainfall-thresholds | ~= 0.1.0 | dice se una pioggia ha superato la soglia che fa franare | [documentazione](https://agentengineering.it/rainfall-thresholds/) · [GitHub](https://github.com/agent-engineering-studio/rainfall-thresholds) |
| ispra-idrogeo | ~= 0.7.0 | scarica le frane censite e le aree a pericolo di ISPRA | [documentazione](https://agentengineering.it/ispra-idrogeo/) · [GitHub](https://github.com/agent-engineering-studio/ispra-idrogeo) |
| copernicus-ems | ~= 0.7.1 | scarica le aree allagate cartografate dal satellite dopo un disastro | [documentazione](https://agentengineering.it/copernicus-ems/) · [GitHub](https://github.com/agent-engineering-studio/copernicus-ems) |
| egms-client | ~= 0.7.0 | scarica le mappe europee del terreno che si muove | [documentazione](https://agentengineering.it/egms-client/) · [GitHub](https://github.com/agent-engineering-studio/egms-client) |
| firms-client | ~= 0.5.0 | scarica i fuochi visti dal satellite e separa gli incendi dalle fonti di calore fisse | [documentazione](https://agentengineering.it/firms-client/) · [GitHub](https://github.com/agent-engineering-studio/firms-client) |
| imageserver-export | ~= 0.2.0 | ricompone le mappe europee del suolo (cemento, alberi, acqua) | [documentazione](https://agentengineering.it/imageserver-export/) · [GitHub](https://github.com/agent-engineering-studio/imageserver-export) |
| ingv-shakemap | ~= 0.2.0 | legge quanto ha tremato il suolo dopo un terremoto | [documentazione](https://agentengineering.it/ingv-shakemap/) · [GitHub](https://github.com/agent-engineering-studio/ingv-shakemap) |
| dpc-radar | ~= 0.2.1 | legge la pioggia del radar della Protezione civile e i bollettini | [documentazione](https://agentengineering.it/dpc-radar/) · [GitHub](https://github.com/agent-engineering-studio/dpc-radar) |
| glofas-ewds | ~= 0.2.0 | scarica la portata prevista e storica dei fiumi | [documentazione](https://agentengineering.it/glofas-ewds/) · [GitHub](https://github.com/agent-engineering-studio/glofas-ewds) |

??? note "Per chi sviluppa: dove sono usate"
    | Libreria | Extra installati | File principale in Limen |
    |---|---|---|
    | fwi-chain | — | `src/limen/core/scoring/wildfire/`, `src/limen/cli/fwi_backfill.py`, `src/limen/data/repos/fwi_state_repo.py` |
    | effis-client | `raster` | `src/limen/integrations/effis/` |
    | rainfall-thresholds | — | `src/limen/core/scoring/caine.py` |
    | ispra-idrogeo | — | `src/limen/integrations/idrogeo/`, `src/limen/api/jobs/dati_download.py` |
    | copernicus-ems | `cdse` | `src/limen/integrations/copernicus_ems/`, `src/limen/cli/backtest_flood.py` |
    | egms-client | `raster` | `src/limen/integrations/egms/` |
    | firms-client | — | `src/limen/integrations/firms/` |
    | imageserver-export | — | `src/limen/integrations/imperviousness/fetch.py` |
    | ingv-shakemap | — | `src/limen/integrations/ingv/` |
    | dpc-radar | `bulletins` | `src/limen/integrations/dpc/` |
    | glofas-ewds | — | `src/limen/integrations/copernicus/` |

    Tutte passano dalla politica di rete di `limen.integrations._http`
    (vedi il capitolo 2).

## Gli strumenti degli altri

Le versioni sono quelle minime richieste da Limen. Gli strumenti segnati
«facoltativo» si installano solo dove servono.

### L'archivio dei dati

| Strumento | Versione | Licenza | A cosa serve | Link |
|---|---|---|---|---|
| PostgreSQL | 16 | PostgreSQL | il database: celle, punteggi, eventi, storia | [postgresql.org](https://www.postgresql.org) |
| PostGIS | 3.5 | GPL-2.0 | insegna la geografia al database | [postgis.net](https://postgis.net) |
| pg_tileserv | — | Apache-2.0 | serve la mappa direttamente dal database | [GitHub](https://github.com/CrunchyData/pg_tileserv) |
| pg_cron, pgvector | — | PostgreSQL | facoltativi: lavori programmati e ricerca per somiglianza dentro il database | [pg_cron](https://github.com/citusdata/pg_cron), [pgvector](https://github.com/pgvector/pgvector) |
| asyncpg | ≥ 0.30 | Apache-2.0 | il collegamento fra il programma e il database | [GitHub](https://github.com/MagicStack/asyncpg) |

### I calcoli sul territorio

| Strumento | Versione | Licenza | A cosa serve | Link |
|---|---|---|---|---|
| rasterio (su GDAL) | ≥ 1.3 | BSD-3-Clause | legge le mappe fatte di pixel: rilievo, vegetazione, cemento | [GitHub](https://github.com/rasterio/rasterio), [gdal.org](https://gdal.org) |
| shapely | ≥ 2.0 | BSD-3-Clause | le forme: contorni, punti, intersezioni | [GitHub](https://github.com/shapely/shapely) |
| geopandas | ≥ 1.0 | BSD-3-Clause | tabelle di forme geografiche | [GitHub](https://github.com/geopandas/geopandas) |
| numpy | ≥ 2.1 | BSD-3-Clause | calcolo numerico | [numpy.org](https://numpy.org) |
| pandas | ≥ 2.2 | BSD-3-Clause | tabelle di numeri, nelle prove e nel modello che impara | [pandas.pydata.org](https://pandas.pydata.org) |
| pydantic, pydantic-settings | ≥ 2.9, ≥ 2.5 | MIT | controllano la forma di ogni dato e di ogni impostazione | [GitHub](https://github.com/pydantic/pydantic) |
| PyYAML | ≥ 6.0 | MIT | legge i file dove stanno pesi e soglie | [pyyaml.org](https://pyyaml.org) |

### Il servizio

| Strumento | Versione | Licenza | A cosa serve | Link |
|---|---|---|---|---|
| FastAPI, uvicorn | ≥ 0.115, ≥ 0.32 | MIT, BSD-3-Clause | rispondono alle domande della mappa e di altri programmi | [fastapi.tiangolo.com](https://fastapi.tiangolo.com) |
| httpx, tenacity | ≥ 0.27, ≥ 9.0 | BSD-3-Clause, Apache-2.0 | le richieste alle fonti esterne e i nuovi tentativi | [httpx](https://github.com/encode/httpx), [tenacity](https://github.com/jd/tenacity) |
| APScheduler | ≥ 4.0.0a5 | MIT | i lavori di ogni ora, di ogni notte e dei tre giorni | [GitHub](https://github.com/agronholm/apscheduler) |
| structlog | ≥ 24.4 | MIT o Apache-2.0 | il registro di quello che succede, leggibile anche da un programma | [GitHub](https://github.com/hynek/structlog) |
| OpenTelemetry | ≥ 1.27 | Apache-2.0 | misura tempi e carichi delle richieste | [GitHub](https://github.com/open-telemetry/opentelemetry-python) |
| aiomqtt, aiosmtplib | ≥ 2.3, ≥ 3.0 | BSD-3-Clause, MIT | gli avvisi via MQTT (un canale per sensori e automazioni) e via email | [aiomqtt](https://github.com/empicano/aiomqtt), [aiosmtplib](https://github.com/cole/aiosmtplib) |
| cryptography | ≥ 43 | Apache-2.0 o BSD-3-Clause | firma la chiave d'accesso al servizio europeo del terreno che si muove | [GitHub](https://github.com/pyca/cryptography) |
| cbor2 | ≥ 6.1 | MIT | legge i messaggi compatti dei sensori | [GitHub](https://github.com/agronholm/cbor2) |
| pmtiles | ≥ 3.4 | BSD-3-Clause | mappe fisse (rilievo, strati) in un unico file | [GitHub](https://github.com/protomaps/PMTiles) |

### Il modello che impara (facoltativo)

| Strumento | Versione | Licenza | A cosa serve | Link |
|---|---|---|---|---|
| LightGBM | ≥ 4.5 | MIT | il modello: alberi di decisione imparati dagli esempi | [documentazione](https://lightgbm.readthedocs.io) |
| scikit-learn | ≥ 1.5 | BSD-3-Clause | misure di qualità e strumenti di prova | [scikit-learn.org](https://scikit-learn.org) |
| Optuna | ≥ 4.0 | MIT | cerca da solo la regolazione migliore | [optuna.org](https://optuna.org) |
| SHAP | ≥ 0.46 | MIT | spiega quanto ha pesato ogni dato in una previsione | [GitHub](https://github.com/shap/shap) |
| MLflow | ≥ 2.16 | Apache-2.0 | registro dei modelli e delle prove | [mlflow.org](https://www.mlflow.org) |
| ONNX Runtime | ≥ 1.20 | MIT | esegue il modello addestrato | [onnxruntime.ai](https://onnxruntime.ai) |
| PyTorch, ONNX | ≥ 2.4, ≥ 1.17 | BSD-3-Clause e altre, Apache-2.0 | modelli di apprendimento profondo, in prova | [pytorch.org](https://pytorch.org), [onnx.ai](https://onnx.ai) |

### L'intelligenza artificiale che scrive (facoltativo)

| Strumento | Versione | Licenza | A cosa serve | Link |
|---|---|---|---|---|
| LiteLLM | — | MIT | un unico ingresso per tutti i modelli di linguaggio, con il tetto di spesa | [documentazione](https://docs.litellm.ai) |
| llama.cpp, llama-swap | — | MIT | fanno girare un modello di linguaggio sul server di Limen | [llama.cpp](https://github.com/ggml-org/llama.cpp), [llama-swap](https://github.com/mostlygeek/llama-swap) |
| SDK Anthropic | ≥ 0.105 | Apache-2.0 | il revisore che controlla che i riassunti siano fedeli ai numeri | [GitHub](https://github.com/anthropics/anthropic-sdk-python) |

### La mappa

| Strumento | Versione | Licenza | A cosa serve | Link |
|---|---|---|---|---|
| React | 19.3 | MIT | l'interfaccia della mappa | [react.dev](https://react.dev) |
| Vite | 5.4 | MIT | prepara la mappa come file pronti da servire | [vite.dev](https://vite.dev) |
| Mantine | 9.6 | MIT | pannelli, menu, moduli | [mantine.dev](https://mantine.dev) |
| MapLibre GL | 4.7 | BSD-3-Clause | disegna la mappa nel browser, senza chiavi d'accesso | [maplibre.org](https://maplibre.org) |
| PMTiles | 3.2 | BSD-3-Clause | legge le mappe fisse da un unico file | [GitHub](https://github.com/protomaps/PMTiles) |

### Il libro

| Strumento | Versione | Licenza | A cosa serve | Link |
|---|---|---|---|---|
| Zensical | ≥ 0.1.0 | MIT | costruisce questo libro come sito | [zensical.org](https://zensical.org) |

??? note "Per chi sviluppa: da dove vengono questi numeri"
    - Python: `[project.dependencies]` e `[dependency-groups]` di
      `pyproject.toml` (gruppi `ml`, `dl`, `agents`, `mcp`, `report`,
      `docs`, `copernicus`, `radar`, `storage`); versioni risolte in
      `uv.lock`.
    - Mappa: `frontend/package.json` (versioni con `^`).
    - PostgreSQL e PostGIS: le immagini dei file compose in `infra/docker/`.
    - Licenze: il campo `license_expression` su PyPI, il campo `license` su
      npm, o la licenza dichiarata dal repository GitHub. Quando una licenza
      cambia in una versione nuova, va aggiornata qui.
