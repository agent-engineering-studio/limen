# La soglia dei pluviometri sulla pioggia del radar (#677)

- Radar: IT-DPC-SRI (FBK su dati DPC, CC BY-SA 4.0, doi:10.5281/zenodo.18637608), 2018-2025, in 4078 punti di frana; 2.2% delle ore-punto non misurato.
- Frane: 1057 di e-ITALICA v4 (CC BY 4.0, doi:10.5281/zenodo.14204473), 3143 di IdroGEO datate al giorno (ISPRA, IFFI ed eventi, CC BY-SA 4.0).
- Momenti ordinari: 395010 (gli stessi punti, ogni 30 giorni con un inizio diverso per punto, ad almeno 15 da una frana lì).
- Punteggio: l'eccesso più alto sulla curva `ITALICA_T5` della macroregione fra gli eventi che toccano le 48 ore prima, ricostruiti come fa il motore.
- Una riga per frana in `misura_soglia_radar_2018_2025.csv`, una per gruppo in `misura_soglia_radar_2018_2025_gruppi.csv`.

Limiti: il radar è letto nel punto della frana, il pluviometro è quello più vicino di e-ITALICA; le durate di e-ITALICA vengono da un'altra ricostruzione degli eventi; i momenti ordinari sono solo in punti dove c'è stata una frana; la mappa del bias è costruita sul 2026, contro il «Merging».

## 1. Le stesse frane, al pluviometro e sul radar

Radar sommato sulla durata dell'evento al pluviometro, fine spostata al meglio entro ±12 ore.

| Regione | Frane | Pluviometro (mm, mediana) | Radar (mm, mediana) | Radar / pluviometro | Con la mappa del bias |
|---|---:|---:|---:|---:|---:|
| Tutte | 970 | 133 | 85 | 0.68 | 0.46 |
| Liguria | 721 | 174 | 115 | 0.72 | 0.48 |
| Tutte senza Liguria | 249 | 84 | 40 | 0.51 | 0.35 |
| Sardegna | 97 | 88 | 70 | 0.81 | 0.56 |
| Marche | 87 | 84 | 30 | 0.29 | 0.17 |
| Piemonte | 12 | 74 | 43 | 0.57 | 0.40 |
| Sicilia | 11 | 72 | 27 | 0.33 | 0.27 |
| Toscana | 8 | 125 | 50 | 0.33 | 0.20 |
| Campania | 7 | 118 | 10 | 0.06 | 0.05 |
| Umbria | 5 | 71 | 53 | 0.75 | 0.58 |

Sopra la curva della macroregione, le stesse frane:

| Insieme | Frane | Pluviometro | Radar | Radar corretto |
|---|---:|---:|---:|---:|
| Tutte | 971 | 95.6% | 66.0% | 51.0% |
| Senza Liguria | 250 | 94.0% | 37.2% | 29.2% |
| Radar affidabile (≥ 0.5) | 934 | 95.5% | 67.0% | 52.0% |

## 2. Frane contro momenti ordinari, sul radar

«Colte al 2 %»: le frane sopra la soglia che accende il 2 % dei momenti ordinari.

### italica: tutte

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 1053 | 61.1% (643) | 9.7% | 33.6% | 47.8% | 0.85 |
| radar corretto | 1053 | 47.1% (496) | 5.2% | 32.4% | 46.4% | 0.85 |

### italica: dove il radar è affidabile (≥ 0.5)

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 1013 | 62.0% (628) | 10.0% | 33.9% | 47.8% | 0.85 |
| radar corretto | 1013 | 48.1% (487) | 5.4% | 33.1% | 47.1% | 0.85 |

### italica: dove il radar è poco affidabile

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 40 | 37.5% (15) | 3.9% | 27.5% | 37.5% | 0.83 |
| radar corretto | 40 | 22.5% (9) | 0.8% | 32.5% | 42.5% | 0.81 |

### italica: senza Liguria

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 269 | 35.3% (95) | 5.5% | 23.4% | 33.5% | 0.82 |
| radar corretto | 269 | 27.5% (74) | 3.1% | 20.8% | 36.1% | 0.81 |

### italica: northern

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 807 | 68.9% (556) | 11.1% | 36.7% | 51.7% | 0.86 |
| radar corretto | 807 | 53.0% (428) | 5.9% | 35.8% | 49.9% | 0.86 |

### italica: central

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 120 | 21.7% (26) | 4.8% | 15.0% | 21.7% | 0.76 |
| radar corretto | 120 | 12.5% (15) | 1.7% | 15.0% | 20.8% | 0.75 |

### italica: southern

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 126 | 48.4% (61) | 5.7% | 32.5% | 43.7% | 0.87 |
| radar corretto | 126 | 42.1% (53) | 4.0% | 27.8% | 49.2% | 0.86 |

### idrogeo: tutte

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 3055 | 35.2% (1074) | 5.7% | 21.1% | 33.4% | 0.73 |
| radar corretto | 3054 | 27.4% (837) | 3.2% | 21.1% | 33.2% | 0.73 |

### idrogeo: dove il radar è affidabile (≥ 0.5)

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 2954 | 35.2% (1040) | 5.8% | 20.7% | 33.2% | 0.73 |
| radar corretto | 2954 | 27.4% (810) | 3.3% | 20.7% | 33.0% | 0.73 |

### idrogeo: dove il radar è poco affidabile

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 101 | 33.7% (34) | 4.2% | 24.8% | 37.6% | 0.75 |
| radar corretto | 100 | 27.0% (27) | 1.8% | 27.0% | 43.0% | 0.76 |

### idrogeo: senza Trentino-Alto Adige

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 1625 | 46.2% (750) | 7.5% | 26.5% | 38.8% | 0.78 |
| radar corretto | 1624 | 35.5% (577) | 4.1% | 24.9% | 39.0% | 0.78 |

### idrogeo: northern

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 2453 | 38.1% (935) | 6.2% | 21.3% | 35.2% | 0.73 |
| radar corretto | 2453 | 30.0% (737) | 3.4% | 22.1% | 35.1% | 0.73 |

### idrogeo: central

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 194 | 30.9% (60) | 5.0% | 17.5% | 30.9% | 0.70 |
| radar corretto | 194 | 18.0% (35) | 2.4% | 17.0% | 27.8% | 0.70 |

### idrogeo: southern

| Pioggia | Frane misurate | Sopra la curva | Ordinarie sopra la curva | Colte al 2% | Colte al 5% | AUC |
|---|---:|---:|---:|---:|---:|---:|
| radar | 408 | 19.4% (79) | 3.2% | 14.7% | 25.5% | 0.77 |
| radar corretto | 407 | 16.0% (65) | 2.5% | 14.0% | 23.3% | 0.77 |

## 3. Una curva tarata sul radar

Inviluppo al 5° percentile (`fit_threshold`) sugli eventi radar delle frane, contro `ITALICA_T5`.

| Insieme | Macroregione | Eventi | alfa | beta | alfa ITALICA_T5 | beta ITALICA_T5 |
|---|---|---:|---:|---:|---:|---:|
| italica | italy | 928 | 0.57 | 0.178 | 7.19 | 0.569 |
| italica | northern | 713 | 0.80 | 0.130 | 6.40 | 0.513 |
| italica | central | 102 | 1.96 | 0.811 | 7.95 | 0.609 |
| italica | southern | 113 | 0.58 | 0.248 | 8.75 | 0.645 |
| idrogeo | italy | 2124 | 0.42 | 0.192 | 7.19 | 0.569 |
| idrogeo | northern | 1696 | 0.35 | 0.170 | 6.40 | 0.513 |
| idrogeo | central | 125 | 0.77 | 0.349 | 7.95 | 0.609 |
| idrogeo | southern | 303 | 1.42 | 0.446 | 8.75 | 0.645 |

- italica: 125 frane senza un evento di pioggia sul radar nelle 48 ore, 4 non misurate.
- idrogeo: 931 frane senza un evento di pioggia sul radar nelle 48 ore, 88 non misurate.

## Provenienza

| | |
|---|---|
| generato | 2026-11-23T19:16:14+00:00 |
| commit | `d6cda0e600590e266c65175381834f3ea5eabbd9` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen misura-soglia-radar` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-fa4dccd` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_ITALICA_CSV` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
