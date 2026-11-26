# Limen backtest incendio — AOI `it-piemonte`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T13:33:57.517336+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **279**
- Celle con almeno un'allerta: **133**
- Hit: **133**, mancati: **146** (celle bruciate); falsi allarmi: **817267** giornate-cella

## Metriche §2.5

- **Hit rate**: 47.67%
- **Tasso di base**: 9.42% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 5.06 volte il tasso di base
- **Carico meteo**: 8.85% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 9.51% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 5.01 volte il carico per cella
- **Giorno peggiore**: 86.49% delle celle dell'AOI in allerta insieme (2026-07-08)
- **FAR per giornata-cella**: 99.97% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 55.2 h

> L'hit rate da solo non dice nulla: un modello che dichiara pericolo
> alto tutti i giorni d'estate lo massimizza senza discriminare. Il
> confronto con il tasso di base è ciò che separa la bravura dalla
> frequenza — sotto 1.0 il modello è peggio del caso.
> Hit rate e preavviso guardano le celle che hanno bruciato, nelle
> 72 h prima di ciascun incendio. Il FAR guarda **tutte** le
> celle dell'AOI per tutta la stagione: un'allerta è falsa se la sua cella
> non brucia nell'orizzonte di preavviso. Con i perimetri EFFIS, che
> censiscono gli incendi grandi, è alto per costruzione: si legge come
> quante allerte arrivano per ogni incendio vero, e si confronta fra
> varianti, non con lo zero.

## Mancati, con la causa

Soglia del livello: punteggio 0.24. Il punteggio è FWI normalizzato per terreno: **meteo sotto la soglia** se l'FWI non ci arrivava neanche col terreno pieno, **terreno sotto la soglia** se ci arrivava e combustibile e pendenza l'hanno tenuto sotto, **cancello degli avvisi** se il livello c'era e la predisposizione no.

- Per causa: meteo sotto la soglia 101, terreno sotto la soglia 45.
- Per terra (CORINE): bosco e seminaturale 108, agricola 25, artificiale 12, acque 1.
- Per mese: 02: 6, 04: 8, 06: 13, 07: 40, 08: 70, 09: 9.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-piemonte|158|120 | 2026-02-18 | 243 | 1.0 | 0.02 | 0.47 | 0.01 | meteo sotto la soglia |
| it-piemonte|158|121 | 2026-02-18 | 311 | 1.0 | 0.02 | 0.67 | 0.01 | meteo sotto la soglia |
| it-piemonte|159|120 | 2026-02-18 | 243 | 1.0 | 0.02 | 0.48 | 0.01 | meteo sotto la soglia |
| it-piemonte|159|121 | 2026-02-18 | 231 | 1.0 | 0.02 | 0.64 | 0.01 | meteo sotto la soglia |
| it-piemonte|160|120 | 2026-02-18 | 231 | 1.0 | 0.02 | 0.65 | 0.01 | meteo sotto la soglia |
| it-piemonte|160|121 | 2026-02-18 | 231 | 1.0 | 0.02 | 0.65 | 0.01 | meteo sotto la soglia |
| it-piemonte|205|158 | 2026-04-05 | 512 | 12.8 | 0.26 | 0.25 | 0.06 | terreno sotto la soglia |
| it-piemonte|200|123 | 2026-04-06 | 324 | 5.4 | 0.11 | 0.91 | 0.10 | meteo sotto la soglia |
| it-piemonte|200|124 | 2026-04-06 | 311 | 5.4 | 0.11 | 0.79 | 0.09 | meteo sotto la soglia |
| it-piemonte|200|125 | 2026-04-06 | 324 | 5.4 | 0.11 | 0.91 | 0.10 | meteo sotto la soglia |
| it-piemonte|200|126 | 2026-04-06 | 324 | 5.4 | 0.11 | 0.91 | 0.10 | meteo sotto la soglia |
| it-piemonte|201|123 | 2026-04-06 | 324 | 5.4 | 0.11 | 0.91 | 0.10 | meteo sotto la soglia |
| it-piemonte|201|124 | 2026-04-06 | 311 | 5.4 | 0.11 | 0.79 | 0.09 | meteo sotto la soglia |
| it-piemonte|201|125 | 2026-04-06 | 324 | 5.4 | 0.11 | 0.91 | 0.10 | meteo sotto la soglia |
| it-piemonte|149|170 | 2026-06-14 | 213 | 16.7 | 0.33 | 0.47 | 0.16 | terreno sotto la soglia |
| it-piemonte|149|171 | 2026-06-14 | 213 | 16.7 | 0.33 | 0.48 | 0.16 | terreno sotto la soglia |
| it-piemonte|150|170 | 2026-06-14 | 121 | 16.7 | 0.33 | 0.32 | 0.11 | terreno sotto la soglia |
| it-piemonte|150|171 | 2026-06-14 | 121 | 16.7 | 0.33 | 0.33 | 0.11 | terreno sotto la soglia |
| it-piemonte|151|170 | 2026-06-14 | 121 | 16.7 | 0.33 | 0.32 | 0.11 | terreno sotto la soglia |
| it-piemonte|151|171 | 2026-06-14 | 311 | 16.7 | 0.33 | 0.66 | 0.22 | terreno sotto la soglia |
| it-piemonte|77|107 | 2026-06-26 | 243 | 19.8 | 0.40 | 0.53 | 0.21 | terreno sotto la soglia |
| it-piemonte|77|108 | 2026-06-26 | 221 | 19.8 | 0.40 | 0.52 | 0.20 | terreno sotto la soglia |
| it-piemonte|78|106 | 2026-06-26 | 243 | 19.8 | 0.40 | 0.53 | 0.21 | terreno sotto la soglia |
| it-piemonte|78|107 | 2026-06-26 | 243 | 19.8 | 0.40 | 0.52 | 0.21 | terreno sotto la soglia |
| it-piemonte|79|106 | 2026-06-26 | 221 | 19.8 | 0.40 | 0.51 | 0.20 | terreno sotto la soglia |
| it-piemonte|79|107 | 2026-06-26 | 243 | 19.8 | 0.40 | 0.51 | 0.20 | terreno sotto la soglia |
| it-piemonte|79|108 | 2026-06-26 | 243 | 19.8 | 0.40 | 0.53 | 0.21 | terreno sotto la soglia |
| it-piemonte|200|127 | 2026-07-01 | 324 | 8.7 | 0.17 | 0.91 | 0.16 | meteo sotto la soglia |
| it-piemonte|160|70 | 2026-07-04 | 313 | 4.7 | 0.09 | 0.87 | 0.08 | meteo sotto la soglia |
| it-piemonte|160|71 | 2026-07-04 | 324 | 4.7 | 0.09 | 0.91 | 0.09 | meteo sotto la soglia |
| it-piemonte|160|72 | 2026-07-04 | 324 | 4.7 | 0.09 | 0.91 | 0.09 | meteo sotto la soglia |
| it-piemonte|160|73 | 2026-07-04 | 313 | 4.7 | 0.09 | 0.87 | 0.08 | meteo sotto la soglia |
| it-piemonte|161|70 | 2026-07-04 | 322 | 4.7 | 0.09 | 0.91 | 0.09 | meteo sotto la soglia |
| it-piemonte|161|71 | 2026-07-04 | 333 | 4.7 | 0.09 | 0.84 | 0.08 | meteo sotto la soglia |
| it-piemonte|161|72 | 2026-07-04 | 333 | 4.7 | 0.09 | 0.84 | 0.08 | meteo sotto la soglia |
| it-piemonte|161|73 | 2026-07-04 | 313 | 4.7 | 0.09 | 0.87 | 0.08 | meteo sotto la soglia |
| it-piemonte|162|70 | 2026-07-04 | 321 | 4.7 | 0.09 | 0.87 | 0.08 | meteo sotto la soglia |
| it-piemonte|162|71 | 2026-07-04 | 333 | 4.7 | 0.09 | 0.84 | 0.08 | meteo sotto la soglia |
| it-piemonte|162|72 | 2026-07-04 | 333 | 4.7 | 0.09 | 0.84 | 0.08 | meteo sotto la soglia |
| it-piemonte|162|73 | 2026-07-04 | 313 | 4.7 | 0.09 | 0.86 | 0.08 | meteo sotto la soglia |
| it-piemonte|163|71 | 2026-07-04 | 333 | 4.7 | 0.09 | 0.84 | 0.08 | meteo sotto la soglia |
| it-piemonte|163|72 | 2026-07-04 | 312 | 4.7 | 0.09 | 1.00 | 0.09 | meteo sotto la soglia |
| it-piemonte|163|73 | 2026-07-04 | 313 | 4.7 | 0.09 | 0.87 | 0.08 | meteo sotto la soglia |
| it-piemonte|197|116 | 2026-07-06 | 311 | 13.6 | 0.27 | 0.79 | 0.21 | terreno sotto la soglia |
| it-piemonte|197|117 | 2026-07-06 | 311 | 13.6 | 0.27 | 0.79 | 0.21 | terreno sotto la soglia |
| it-piemonte|197|118 | 2026-07-06 | 311 | 13.6 | 0.27 | 0.79 | 0.21 | terreno sotto la soglia |
| it-piemonte|198|116 | 2026-07-06 | 313 | 13.6 | 0.27 | 0.88 | 0.24 | terreno sotto la soglia |
| it-piemonte|198|117 | 2026-07-06 | 333 | 13.6 | 0.27 | 0.84 | 0.23 | terreno sotto la soglia |
| it-piemonte|198|118 | 2026-07-06 | 311 | 13.6 | 0.27 | 0.77 | 0.21 | terreno sotto la soglia |
| it-piemonte|199|117 | 2026-07-06 | 333 | 13.6 | 0.27 | 0.84 | 0.23 | terreno sotto la soglia |
| it-piemonte|225|159 | 2026-07-22 | 321 | 8.4 | 0.17 | 0.87 | 0.15 | meteo sotto la soglia |
| it-piemonte|225|160 | 2026-07-22 | 311 | 8.4 | 0.17 | 0.79 | 0.13 | meteo sotto la soglia |
| it-piemonte|225|161 | 2026-07-22 | 321 | 8.4 | 0.17 | 0.87 | 0.15 | meteo sotto la soglia |
| it-piemonte|226|159 | 2026-07-22 | 324 | 8.4 | 0.17 | 0.91 | 0.15 | meteo sotto la soglia |
| it-piemonte|226|160 | 2026-07-22 | 321 | 8.4 | 0.17 | 0.87 | 0.15 | meteo sotto la soglia |
| it-piemonte|226|161 | 2026-07-22 | 321 | 8.4 | 0.17 | 0.87 | 0.15 | meteo sotto la soglia |
| it-piemonte|227|159 | 2026-07-22 | 333 | 6.5 | 0.13 | 0.83 | 0.11 | meteo sotto la soglia |
| it-piemonte|227|160 | 2026-07-22 | 333 | 6.5 | 0.13 | 0.84 | 0.11 | meteo sotto la soglia |
| it-piemonte|227|161 | 2026-07-22 | 322 | 6.5 | 0.13 | 0.91 | 0.12 | meteo sotto la soglia |
| it-piemonte|96|68 | 2026-07-23 | 243 | 25.2 | 0.50 | 0.46 | 0.23 | terreno sotto la soglia |
| it-piemonte|97|68 | 2026-07-23 | 211 | 25.2 | 0.50 | 0.46 | 0.23 | terreno sotto la soglia |
| it-piemonte|97|69 | 2026-07-23 | 211 | 25.2 | 0.50 | 0.46 | 0.23 | terreno sotto la soglia |
| it-piemonte|98|68 | 2026-07-23 | 211 | 25.2 | 0.50 | 0.47 | 0.24 | terreno sotto la soglia |
| it-piemonte|98|69 | 2026-07-23 | 211 | 25.2 | 0.50 | 0.46 | 0.23 | terreno sotto la soglia |
| it-piemonte|121|32 | 2026-07-26 | 243 | 16.5 | 0.33 | 0.57 | 0.19 | terreno sotto la soglia |
| it-piemonte|121|33 | 2026-07-26 | 112 | 16.5 | 0.33 | 0.33 | 0.11 | terreno sotto la soglia |
| it-piemonte|122|32 | 2026-07-26 | 243 | 16.5 | 0.33 | 0.55 | 0.18 | terreno sotto la soglia |
| it-piemonte|183|119 | 2026-08-04 | 311 | 0.5 | 0.01 | 0.79 | 0.01 | meteo sotto la soglia |
| it-piemonte|184|119 | 2026-08-04 | 321 | 0.5 | 0.01 | 0.87 | 0.01 | meteo sotto la soglia |
| it-piemonte|157|78 | 2026-08-05 | 311 | 0.7 | 0.01 | 0.77 | 0.01 | meteo sotto la soglia |
| it-piemonte|157|79 | 2026-08-05 | 322 | 0.7 | 0.01 | 0.88 | 0.01 | meteo sotto la soglia |
| it-piemonte|158|77 | 2026-08-05 | 333 | 0.7 | 0.01 | 0.84 | 0.01 | meteo sotto la soglia |
| it-piemonte|158|78 | 2026-08-05 | 333 | 0.7 | 0.01 | 0.84 | 0.01 | meteo sotto la soglia |
| it-piemonte|158|79 | 2026-08-05 | 333 | 0.7 | 0.01 | 0.84 | 0.01 | meteo sotto la soglia |
| it-piemonte|159|77 | 2026-08-05 | 333 | 0.7 | 0.01 | 0.83 | 0.01 | meteo sotto la soglia |
| it-piemonte|159|78 | 2026-08-05 | 333 | 0.7 | 0.01 | 0.84 | 0.01 | meteo sotto la soglia |
| it-piemonte|159|79 | 2026-08-05 | 333 | 0.7 | 0.01 | 0.84 | 0.01 | meteo sotto la soglia |
| it-piemonte|215|128 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|215|129 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|216|126 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|216|127 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|216|128 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|216|129 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|216|130 | 2026-08-08 | 243 | 10.5 | 0.21 | 0.57 | 0.12 | meteo sotto la soglia |
| it-piemonte|216|131 | 2026-08-08 | 231 | 10.5 | 0.21 | 0.64 | 0.13 | meteo sotto la soglia |
| it-piemonte|217|126 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|217|127 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|217|128 | 2026-08-08 | 324 | 10.5 | 0.21 | 0.91 | 0.19 | meteo sotto la soglia |
| it-piemonte|217|129 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|217|130 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.78 | 0.17 | meteo sotto la soglia |
| it-piemonte|217|131 | 2026-08-08 | 231 | 10.5 | 0.21 | 0.64 | 0.13 | meteo sotto la soglia |
| it-piemonte|218|125 | 2026-08-08 | 313 | 10.5 | 0.21 | 0.88 | 0.19 | meteo sotto la soglia |
| it-piemonte|218|126 | 2026-08-08 | 312 | 10.5 | 0.21 | 1.00 | 0.21 | meteo sotto la soglia |
| it-piemonte|218|127 | 2026-08-08 | 312 | 10.5 | 0.21 | 1.00 | 0.21 | meteo sotto la soglia |
| it-piemonte|218|128 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|218|129 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|218|130 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.75 | 0.16 | meteo sotto la soglia |
| it-piemonte|218|131 | 2026-08-08 | 331 | 10.5 | 0.21 | 0.34 | 0.07 | meteo sotto la soglia |
| it-piemonte|219|127 | 2026-08-08 | 313 | 10.5 | 0.21 | 0.88 | 0.19 | meteo sotto la soglia |
| it-piemonte|219|130 | 2026-08-08 | 311 | 10.5 | 0.21 | 0.75 | 0.16 | meteo sotto la soglia |
| it-piemonte|200|128 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|200|129 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|201|126 | 2026-08-09 | 324 | 10.5 | 0.21 | 0.91 | 0.19 | meteo sotto la soglia |
| it-piemonte|201|127 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|201|128 | 2026-08-09 | 321 | 10.5 | 0.21 | 0.86 | 0.18 | meteo sotto la soglia |
| it-piemonte|201|129 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|202|123 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|202|124 | 2026-08-09 | 312 | 10.5 | 0.21 | 1.00 | 0.21 | meteo sotto la soglia |
| it-piemonte|202|125 | 2026-08-09 | 312 | 10.5 | 0.21 | 1.00 | 0.21 | meteo sotto la soglia |
| it-piemonte|202|126 | 2026-08-09 | 321 | 10.5 | 0.21 | 0.87 | 0.18 | meteo sotto la soglia |
| it-piemonte|202|127 | 2026-08-09 | 321 | 10.5 | 0.21 | 0.87 | 0.18 | meteo sotto la soglia |
| it-piemonte|202|128 | 2026-08-09 | 321 | 10.5 | 0.21 | 0.86 | 0.18 | meteo sotto la soglia |
| it-piemonte|203|124 | 2026-08-09 | 313 | 10.5 | 0.21 | 0.88 | 0.19 | meteo sotto la soglia |
| it-piemonte|203|126 | 2026-08-09 | 313 | 10.5 | 0.21 | 0.88 | 0.19 | meteo sotto la soglia |
| it-piemonte|203|127 | 2026-08-09 | 321 | 10.5 | 0.21 | 0.87 | 0.18 | meteo sotto la soglia |
| it-piemonte|215|120 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|215|121 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|215|122 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|215|123 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|216|120 | 2026-08-09 | 321 | 10.5 | 0.21 | 0.87 | 0.18 | meteo sotto la soglia |
| it-piemonte|216|121 | 2026-08-09 | 321 | 10.5 | 0.21 | 0.87 | 0.18 | meteo sotto la soglia |
| it-piemonte|216|122 | 2026-08-09 | 333 | 10.5 | 0.21 | 0.84 | 0.18 | meteo sotto la soglia |
| it-piemonte|216|123 | 2026-08-09 | 333 | 10.5 | 0.21 | 0.84 | 0.18 | meteo sotto la soglia |
| it-piemonte|216|124 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.79 | 0.17 | meteo sotto la soglia |
| it-piemonte|216|125 | 2026-08-09 | 311 | 10.5 | 0.21 | 0.78 | 0.16 | meteo sotto la soglia |
| it-piemonte|217|121 | 2026-08-09 | 324 | 10.5 | 0.21 | 0.91 | 0.19 | meteo sotto la soglia |
| it-piemonte|217|122 | 2026-08-09 | 313 | 10.5 | 0.21 | 0.88 | 0.19 | meteo sotto la soglia |
| it-piemonte|217|123 | 2026-08-09 | 313 | 10.5 | 0.21 | 0.88 | 0.19 | meteo sotto la soglia |
| it-piemonte|217|124 | 2026-08-09 | 313 | 10.5 | 0.21 | 0.88 | 0.19 | meteo sotto la soglia |
| it-piemonte|217|125 | 2026-08-09 | 313 | 10.5 | 0.21 | 0.87 | 0.18 | meteo sotto la soglia |
| it-piemonte|189|126 | 2026-08-10 | 311 | 13.7 | 0.27 | 0.78 | 0.21 | terreno sotto la soglia |
| it-piemonte|190|124 | 2026-08-10 | 311 | 13.7 | 0.27 | 0.79 | 0.22 | terreno sotto la soglia |
| it-piemonte|190|125 | 2026-08-10 | 311 | 13.7 | 0.27 | 0.79 | 0.22 | terreno sotto la soglia |
| it-piemonte|190|126 | 2026-08-10 | 311 | 13.7 | 0.27 | 0.78 | 0.21 | terreno sotto la soglia |
| it-piemonte|191|124 | 2026-08-10 | 311 | 13.7 | 0.27 | 0.79 | 0.22 | terreno sotto la soglia |
| it-piemonte|191|125 | 2026-08-10 | 311 | 13.7 | 0.27 | 0.79 | 0.22 | terreno sotto la soglia |
| it-piemonte|191|126 | 2026-08-10 | 311 | 13.7 | 0.27 | 0.79 | 0.22 | terreno sotto la soglia |
| it-piemonte|106|77 | 2026-09-24 | 112 | 14.4 | 0.29 | 0.29 | 0.08 | terreno sotto la soglia |
| it-piemonte|106|78 | 2026-09-24 | 112 | 14.9 | 0.30 | 0.28 | 0.08 | terreno sotto la soglia |
| it-piemonte|107|76 | 2026-09-24 | 121 | 14.4 | 0.29 | 0.31 | 0.09 | terreno sotto la soglia |
| it-piemonte|107|77 | 2026-09-24 | 121 | 14.4 | 0.29 | 0.31 | 0.09 | terreno sotto la soglia |
| it-piemonte|107|78 | 2026-09-24 | 121 | 14.9 | 0.30 | 0.31 | 0.09 | terreno sotto la soglia |
| it-piemonte|108|76 | 2026-09-24 | 141 | 14.4 | 0.29 | 0.31 | 0.09 | terreno sotto la soglia |
| it-piemonte|108|77 | 2026-09-24 | 121 | 14.4 | 0.29 | 0.31 | 0.09 | terreno sotto la soglia |
| it-piemonte|108|78 | 2026-09-24 | 112 | 14.9 | 0.30 | 0.28 | 0.08 | terreno sotto la soglia |
| it-piemonte|106|76 | 2026-09-28 | 211 | 15.4 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T13:33:57+00:00 |
| commit | `626506428402e7df05320c5296a6e9009362d538` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-piemonte` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-25` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-ecddbd8` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
