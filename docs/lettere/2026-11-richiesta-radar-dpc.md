# Richiesta al Dipartimento della Protezione Civile sui dati del radar

Testo pronto da inviare al Dipartimento della Protezione Civile (#625, #626,
#627, #628). Il destinatario va preso dai contatti sul sito del Dipartimento
(<https://www.protezionecivile.gov.it>; la PEC, se si vuole una risposta
protocollata). Le parti fra parentesi quadre le completa chi invia. I numeri
vengono dal [report](../misure/misura_radar_2026-06-10_2026-11-15.md) del
16 novembre 2026.

Quando arriva la risposta: archiviarla (PDF o link) nelle issue #625-#628,
aggiornare la tabella «Gap e come chiuderli» dell'[appendice E](../book/appendice-e-radar.md)
e, se il Dipartimento indica un limite di richieste, confrontarlo con il conto
scritto nel [runbook](../runbook.md#richieste-al-servizio-radar-del-dpc).

---

**Oggetto:** Dati radar della piattaforma Radar-DPC — quattro richieste da un progetto open source che li usa ogni giorno

Gentili responsabili della piattaforma Radar-DPC,

scrivo per conto del progetto **Limen**, un sistema open source (licenza
EUPL-1.2, codice pubblico su https://github.com/agent-engineering-studio/limen)
che stima ogni ora il pericolo di frana, alluvione e incendio boschivo su una
griglia di celle da 1 km² del territorio italiano, usando solo dati pubblici.

La pioggia caduta la leggiamo dal vostro servizio
`radar-api.protezionecivile.it`: l'intensità istantanea (SRI) per i
temporali, le cumulate «Merging» di radar e pluviometri (CUM3, CUM6, CUM12,
CUM24) per le frane e le piene, la cumulata di un'ora del solo radar (SRT1).
Citiamo la fonte come «Dipartimento della Protezione Civile» con la licenza
CC BY-SA 4.0. Il codice che legge il servizio è pubblicato a parte, come
libreria aperta: https://github.com/agent-engineering-studio/dpc-radar.

Per noi il «Merging» è la migliore misura di pioggia disponibile in Italia,
e vi ringraziamo di pubblicarla. Usandola ogni giorno abbiamo incontrato
quattro limiti che solo voi potete togliere.

1. **Un archivio permanente del «Merging».** Il servizio conserva circa
   cinque mesi di immagini; quelle più vecchie non si possono più scaricare.
   Il 16 novembre 2026 il servizio dava ancora le immagini dal 9 giugno:
   ne abbiamo salvate 5.109 fra CUM3 e SRT1, e da ora le salviamo ogni
   notte. Ma quello che è stato pubblicato prima è perso, e ogni gruppo di
   ricerca si trova nella stessa condizione. Per il solo radar esiste l'archivio IT-DPC-SRI, pubblicato su
   Zenodo con un DOI (https://doi.org/10.5281/zenodo.18637608). È possibile
   pubblicare allo stesso modo l'archivio storico delle cumulate «Merging»?
2. **Un «Merging» di un'ora.** Le piene improvvise si decidono in un'ora, ma
   la cumulata più breve corretta con i pluviometri è di tre ore. Oggi
   ricostruiamo l'ora ripartendo la CUM3 secondo la SRT1: è una stima
   nostra, non un vostro prodotto. È previsto, o è possibile, pubblicare la
   cumulata oraria corretta con i pluviometri accanto a quelle di 3-24 ore?
3. **La documentazione e le condizioni d'uso del servizio.** Non abbiamo
   trovato un manuale pubblico del servizio né una pagina che dica quante
   richieste è lecito fare. Limen fa oggi meno di 1.000 richieste al giorno
   per installazione (circa una ogni due minuti), più il recupero iniziale
   dell'archivio, di notte, limitato a 1.500 immagini per notte. Vi chiediamo:
   esiste una documentazione del servizio? C'è un limite di richieste che
   dobbiamo rispettare? C'è un recapito a cui segnalare un'anomalia nei dati,
   come quella delle cumulate fra l'11 ottobre e il 3 novembre 2026?
4. **Una mappa di qualità.** Il radar non vede allo stesso modo dappertutto:
   lontano dagli impianti e dietro i rilievi vede meno. Oggi una pioggia
   vista male arriva uguale a una vista bene. È possibile pubblicare la mappa
   della copertura e della qualità del mosaico, e l'elenco (o la posizione)
   dei pluviometri che entrano nel «Merging»? Una stima nostra, fatta
   confrontando SRT1 e CUM3 su 155 giorni, indica i riquadri a ovest della
   Sicilia come quelli dove il solo radar vede meno. La stessa stima mostra,
   in due riquadri vicino a Foggia (circa 15,4°E 41,25°N), pioggia nel
   «Merging» in giorni in cui il radar e i riquadri vicini non ne vedono:
   ve lo segnaliamo nel caso sia un pluviometro da controllare.

Se una di queste cose esiste già e non l'abbiamo trovata, ci basta
l'indicazione di dove cercarla. Tutto quello che misuriamo su questi dati è
pubblico, e siamo a disposizione per condividerlo.

Ringraziamo per l'attenzione e per il lavoro di pubblicazione dei dati radar
nazionali.

Cordiali saluti,

[Nome e cognome]
[Ruolo nel progetto Limen]
[Recapito per la risposta]
