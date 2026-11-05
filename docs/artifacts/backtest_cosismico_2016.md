# Limen backtest cosismico — scuotimento ShakeMap contro frane sismoindotte

Generato: 2026-11-04T15:39:14.248800+00:00
Soglia di E (`seismic.pga_min_g`): **0.02 g**

## Eventi

| Evento | ShakeMap | Frane | In mappa | Casi | Punti su terra | PGA mediana casi |
|---|---|---|---|---|---|---|
| 7073641 | v1 automatic | 145 | 145 | 90 | 66770 | 0.313 g |
| 8669321 | v5 automatic | 235 | 235 | 70 | 137414 | 0.315 g |
| 8863681 | v2 automatic | 378 | 378 | 132 | 159060 | 0.404 g |

## AUC: le frane stanno dove ha tremato di più?

0,5 è il caso; 1 separa perfettamente. `vicinanza` è la sola distanza
dall'epicentro: è il riferimento che la ShakeMap deve battere.

### Su tutta la terra in mappa

| Evento | PGA | PGV | MMI | vicinanza |
|---|---|---|---|---|
| 7073641 | 0.970 | 0.970 | 0.969 | 0.979 |
| 8669321 | 0.993 | 0.991 | 0.991 | 0.997 |
| 8863681 | 0.988 | 0.988 | 0.987 | 0.989 |
| **media pesata sui casi** | **0.983** | **0.983** | **0.983** | **0.988** |

### Nel campo vicino: solo dove E è acceso (PGA ≥ 0.02 g)

| Evento | PGA | PGV | MMI | vicinanza |
|---|---|---|---|---|
| 7073641 | 0.920 | 0.920 | 0.919 | 0.946 |
| 8669321 | 0.951 | 0.942 | 0.942 | 0.977 |
| 8863681 | 0.960 | 0.960 | 0.959 | 0.965 |
| **media pesata sui casi** | **0.946** | **0.943** | **0.943** | **0.962** |

La seconda tabella è quella che decide: sull'intera mappa vince
qualunque misura che cresca verso l'epicentro, anche la sola distanza.

## Soglie di PGA: recall, carico, lift

Recall: la quota di punti franati sopra soglia. Carico: la quota di
territorio in mappa sopra soglia. Lift = recall / carico: quante volte
la soglia concentra le frane rispetto al caso.

| Evento | PGA ≥ | Recall | Carico | Lift |
|---|---|---|---|---|
| 7073641 | 0.02 g ← E | 100.0% | 37.8% | 2.64 |
| 7073641 | 0.05 g | 97.8% | 16.0% | 6.12 |
| 7073641 | 0.1 g | 85.6% | 6.6% | 13.05 |
| 7073641 | 0.2 g | 77.8% | 3.0% | 26.24 |
| 7073641 | 0.3 g | 57.8% | 1.4% | 40.95 |
| 8669321 | 0.02 g ← E | 100.0% | 14.9% | 6.72 |
| 8669321 | 0.05 g | 97.1% | 6.4% | 15.28 |
| 8669321 | 0.1 g | 90.0% | 2.9% | 31.55 |
| 8669321 | 0.2 g | 82.9% | 0.8% | 99.35 |
| 8669321 | 0.3 g | 60.0% | 0.3% | 217.54 |
| 8863681 | 0.02 g ← E | 99.2% | 21.6% | 4.59 |
| 8863681 | 0.05 g | 99.2% | 10.8% | 9.21 |
| 8863681 | 0.1 g | 98.5% | 4.9% | 20.25 |
| 8863681 | 0.2 g | 89.4% | 1.8% | 48.78 |
| 8863681 | 0.3 g | 73.5% | 1.1% | 66.87 |

> Lo scuotimento solo, senza il terreno: una frana chiede un versante,
> e un AUC alto della PGA in pianura non vuol dire nulla. La pendenza
> entra con il modello «ground failure», sulle celle di Limen.


## Lettura (4 novembre 2026)

Tre eventi della sequenza 2016, inventari CEDIT (CERI Sapienza, USGS data
release CC0): 145 frane per Amatrice, 235 per Visso, 378 per Norcia, quasi
tutte crolli in roccia. ShakeMap INGV correnti, tutte ancora `automatic`.

1. **Lo scuotimento concentra le frane, e molto.** Sopra 0,1 g sta l'86-98 %
   dei punti franati su appena il 3-7 % del territorio in mappa (lift 13-32).
   E dice qualcosa di vero: dove la ShakeMap trema forte, i versanti cedono.
2. **La soglia di E è troppo bassa.** A `pga_min_g` = 0,02 g la recall è
   99-100 %, ma il carico è il 15-38 % della terra in mappa: E si accende su
   un territorio da tre a sette volte più largo del necessario. È coerente
   con le ore-cella in allerta ×23 del backtest #287. A 0,1 g la recall resta
   86-98 % con un carico di un quinto.
3. **La ShakeMap non batte la sola distanza dall'epicentro.** AUC nel campo
   vicino: PGA 0,946, PGV 0,943, distanza 0,962. Su questi eventi il dettaglio
   spaziale della mappa non aggiunge nulla, nel ranking, a un cerchio attorno
   all'epicentro. Due cause possibili, che questi dati non separano:
   le mappe sono `automatic` con sorgente puntiforme (il campo di PGA è quasi
   radiale), e l'inventario viene da sopralluoghi, che si concentrano vicino
   all'epicentro (mediana 5-14 km, 90 % entro 25 km).
4. **PGV non fa meglio di PGA**, a differenza di quanto trova Nowicki Jessee
   (2018) su scala globale: a questa distanza le due misure sono quasi
   proporzionali.

Cosa *non* dice: niente sul terreno (pendenza, litologia), niente sul
decadimento τ (le frane cosismiche sono istantanee), niente fuori da una
sequenza appenninica di tre eventi.

### Verifica indipendente: L'Aquila 2009

La soglia di 0,1 g è stata letta sugli stessi tre eventi su cui è misurata,
quindi era ottimistica. Rigirata su un terremoto diverso: L'Aquila, 6 aprile
2009, Mw 6.1 (INGV 1895389, ShakeMap v1 `automatic`), inventario CEDIT di 94
frane (USGS, CC0), mediana 10 km dall'epicentro.

| PGA ≥ | Recall | Carico | Lift |
|---|---|---|---|
| 0,02 g ← E | 100 % | 15,3 % | 6,5 |
| 0,05 g | 98,5 % | 5,6 % | 17,6 |
| **0,1 g** | **97,1 %** | **2,5 %** | **39,0** |
| 0,2 g | 70,6 % | 0,9 % | 80,4 |
| 0,3 g | 19,1 % | 0,2 % | 104,1 |

AUC nel campo vicino: PGA 0,950, PGV 0,948, MMI 0,948, distanza 0,933.

* **0,1 g regge**: 97 % delle frane su un quarantesimo del territorio in
  mappa, in linea con i tre eventi del 2016 (86-98 % su 3-7 %).
* **Più in alto si perde molto**: a 0,2 g la recall scende al 71 %, a 0,3 g
  al 19 %. 0,1 g è il ginocchio della curva, non un valore fra tanti.
* **Qui la ShakeMap batte la distanza** (0,950 contro 0,933): sul 2016 no.
  La conclusione 3 sopra vale per quella sequenza, non in generale.

Prossimi passi proposti:

* rigiocare il backtest #287 con `pga_min_g` = 0,1 g per misurare quanto
  scende il carico in allerta; è un cambio di soglia nella YAML, non di codice.
  La soglia ora ha una verifica indipendente (L'Aquila 2009);
* aggiungere la pendenza delle celle di Limen (sul server, dove i fattori
  statici ci sono) e vedere se scuotimento × pendenza batte la distanza:
  è la domanda del modello «ground failure».
