# Tre termini d'innesco a parità di carico (#676)

- Finestre: le dodici della #122; taratura it-campania, it-liguria, it-lombardia, it-piemonte, it-sicilia, it-toscana, le altre in verifica.
- Frane: e-ITALICA (sorgenti IR, NR), una per punto e istante. Colta se il suo nodo supera la soglia in un istante delle 72 ore prima (per una data senza ora, fino alla fine di quel giorno).
- Unità ordinarie: 370380 nodi-istanti (nodi a 0,1° più vicini a una cella dell'AOI, un istante ogni 6 ore), con o senza frane.
- Letture: **caine** = eccesso in decadi sulla curva della macroregione, eventi delle 48 ore prima, non tagliato a zero (-99 senza evento); **cumulata** = mm delle 24 ore; **relativa** = cumulata / q0.999 della cumulata del nodo (`limen clima-pioggia`, anni prima di ogni finestra).
- Letture non misurate (nodo senza pioggia dall'archivio, o senza riferimento): caine 0, cumulata 0, relativa 0. Restano fuori, mai contate come zero.
- Misure: `rainfall_thresholds.measure` (`skill_at_budget`, `cutoff_at_budget`, `skill`, `auc`).
- Una riga per frana in `misura_innesco_122.csv`.

## Tutte le frane (643 frane)

### A parità di carico in ogni regione (ordinamento)

| Lettura | taratura al 2% | verifica al 2% | taratura al 5% | verifica al 5% |
|---|---|---|---|---|
| caine | 95/323 = 29,4%, 44 allerte per frana colta | 110/320 = 34,4%, 30 allerte per frana colta | 168/323 = 52,0%, 62 allerte per frana colta | 233/320 = 72,8%, 35 allerte per frana colta |
| cumulata | 158/323 = 48,9%, 26 allerte per frana colta | 199/320 = 62,2%, 17 allerte per frana colta | 214/323 = 66,3%, 48 allerte per frana colta | 247/320 = 77,2%, 33 allerte per frana colta |
| relativa | 136/323 = 42,1%, 30 allerte per frana colta | 185/320 = 57,8%, 18 allerte per frana colta | 207/323 = 64,1%, 50 allerte per frana colta | 250/320 = 78,1%, 33 allerte per frana colta |

### Soglia nazionale scelta in taratura, applicata alla verifica (scala)

| Lettura | Carico | Soglia | Taratura | Verifica | Verifica: quota in allerta |
|---|---|---|---|---|---|
| caine | 2% | 0,37 | 104/323 = 32,2%, 40 allerte per frana colta | 16/320 = 5,0%, 59 allerte per frana colta | 0,6% |
| caine | 5% | 0,23 | 168/323 = 52,0%, 61 allerte per frana colta | 44/320 = 13,8%, 56 allerte per frana colta | 1,5% |
| cumulata | 2% | 53,90 | 136/323 = 42,1%, 30 allerte per frana colta | 12/320 = 3,8%, 47 allerte per frana colta | 0,3% |
| cumulata | 5% | 37,00 | 236/323 = 73,1%, 44 allerte per frana colta | 67/320 = 20,9%, 33 allerte per frana colta | 1,3% |
| relativa | 2% | 0,86 | 129/323 = 39,9%, 32 allerte per frana colta | 58/320 = 18,1%, 38 allerte per frana colta | 1,3% |
| relativa | 5% | 0,62 | 208/323 = 64,4%, 50 allerte per frana colta | 228/320 = 71,2%, 21 allerte per frana colta | 2,9% |

### AUC media per finestra

Più alta che nella #243: il punteggio di una frana è il massimo delle 72 ore prima, quello di un'unità ordinaria un istante solo. Vale per confrontare le letture fra loro, non come numero assoluto.

| Lettura | Taratura | Verifica |
|---|---|---|
| caine | 0,92 | 0,91 |
| cumulata | 0,95 | 0,94 |
| relativa | 0,95 | 0,94 |

### Per regione, al 5 % in ogni regione

| Regione | Gruppo | Nodi | Frane | caine | cumulata | relativa |
|---|---|---|---|---|---|---|
| it-liguria (2019-11) | taratura | 103 | 140 | 59 | 76 | 67 |
| it-piemonte (2009-04) | taratura | 356 | 53 | 31 | 40 | 43 |
| it-sicilia (2009-01) | taratura | 346 | 36 | 25 | 27 | 26 |
| it-toscana (2008-12) | taratura | 339 | 36 | 23 | 29 | 29 |
| it-lombardia (2014-11) | taratura | 349 | 28 | 15 | 24 | 24 |
| it-campania (2009-01) | taratura | 198 | 30 | 15 | 18 | 18 |
| it-marche (2014-05) | verifica | 138 | 180 | 153 | 166 | 166 |
| it-calabria (2009-01) | verifica | 207 | 35 | 28 | 28 | 31 |
| it-lazio (2010-05) | verifica | 250 | 28 | 4 | 4 | 4 |
| it-umbria (2008-12) | verifica | 127 | 24 | 4 | 4 | 5 |
| it-sardegna (2018-05) | verifica | 324 | 31 | 22 | 23 | 22 |
| it-puglia (2009-03) | verifica | 276 | 22 | 22 | 22 | 22 |

## Solo le frane datate al giorno (T1, T2) (420 frane)

### A parità di carico in ogni regione (ordinamento)

| Lettura | taratura al 2% | verifica al 2% | taratura al 5% | verifica al 5% |
|---|---|---|---|---|
| caine | 66/261 = 25,3%, 63 allerte per frana colta | 50/159 = 31,4%, 66 allerte per frana colta | 125/261 = 47,9%, 83 allerte per frana colta | 83/159 = 52,2%, 99 allerte per frana colta |
| cumulata | 121/261 = 46,4%, 34 allerte per frana colta | 58/159 = 36,5%, 57 allerte per frana colta | 157/261 = 60,2%, 66 allerte per frana colta | 97/159 = 61,0%, 85 allerte per frana colta |
| relativa | 97/261 = 37,2%, 43 allerte per frana colta | 61/159 = 38,4%, 54 allerte per frana colta | 152/261 = 58,2%, 68 allerte per frana colta | 98/159 = 61,6%, 84 allerte per frana colta |

### Soglia nazionale scelta in taratura, applicata alla verifica (scala)

| Lettura | Carico | Soglia | Taratura | Verifica | Verifica: quota in allerta |
|---|---|---|---|---|---|
| caine | 2% | 0,37 | 78/261 = 29,9%, 53 allerte per frana colta | 14/159 = 8,8%, 67 allerte per frana colta | 0,6% |
| caine | 5% | 0,23 | 128/261 = 49,0%, 81 allerte per frana colta | 39/159 = 24,5%, 63 allerte per frana colta | 1,5% |
| cumulata | 2% | 53,90 | 102/261 = 39,1%, 41 allerte per frana colta | 10/159 = 6,3%, 56 allerte per frana colta | 0,3% |
| cumulata | 5% | 37,00 | 185/261 = 70,9%, 56 allerte per frana colta | 44/159 = 27,7%, 50 allerte per frana colta | 1,3% |
| relativa | 2% | 0,86 | 92/261 = 35,2%, 45 allerte per frana colta | 49/159 = 30,8%, 44 allerte per frana colta | 1,3% |
| relativa | 5% | 0,62 | 155/261 = 59,4%, 67 allerte per frana colta | 84/159 = 52,8%, 57 allerte per frana colta | 2,9% |

### AUC media per finestra

Più alta che nella #243: il punteggio di una frana è il massimo delle 72 ore prima, quello di un'unità ordinaria un istante solo. Vale per confrontare le letture fra loro, non come numero assoluto.

| Lettura | Taratura | Verifica |
|---|---|---|
| caine | 0,92 | 0,90 |
| cumulata | 0,95 | 0,93 |
| relativa | 0,94 | 0,93 |

### Per regione, al 5 % in ogni regione

| Regione | Gruppo | Nodi | Frane | caine | cumulata | relativa |
|---|---|---|---|---|---|---|
| it-liguria (2019-11) | taratura | 103 | 136 | 57 | 72 | 64 |
| it-piemonte (2009-04) | taratura | 356 | 37 | 16 | 25 | 28 |
| it-sicilia (2009-01) | taratura | 346 | 30 | 20 | 22 | 21 |
| it-toscana (2008-12) | taratura | 339 | 15 | 10 | 10 | 10 |
| it-lombardia (2014-11) | taratura | 349 | 15 | 9 | 12 | 13 |
| it-campania (2009-01) | taratura | 198 | 28 | 13 | 16 | 16 |
| it-marche (2014-05) | verifica | 138 | 48 | 21 | 34 | 34 |
| it-calabria (2009-01) | verifica | 207 | 28 | 23 | 23 | 24 |
| it-lazio (2010-05) | verifica | 250 | 24 | 3 | 3 | 3 |
| it-umbria (2008-12) | verifica | 127 | 18 | 4 | 4 | 5 |
| it-sardegna (2018-05) | verifica | 324 | 31 | 22 | 23 | 22 |
| it-puglia (2009-03) | verifica | 276 | 10 | 10 | 10 | 10 |

## Provenienza

| | |
|---|---|
| generato | 2026-11-24T18:14:12+00:00 |
| commit | `336752b3b6d1dae9ada7b538458845dcdba1a84a` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen misura-innesco` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_CLIMA_PIOGGIA` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-fa4dccd` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
