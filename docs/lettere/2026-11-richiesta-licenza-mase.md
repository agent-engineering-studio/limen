# Richiesta di chiarimento sulla licenza della Carta geolitologica d'Italia

Testo pronto da inviare al Geoportale Nazionale del Ministero dell'Ambiente e
della Sicurezza Energetica (#495). Il destinatario va preso dalla pagina
[note legali](https://gn.mase.gov.it/portale/note-legali) o dai contatti del
Geoportale (PEC del Ministero, se si vuole una risposta protocollata). Le parti
fra parentesi quadre le completa chi invia.

Quando arriva la risposta: archiviarla (PDF o link) nella voce #495 della
raccolta #618, scriverla come commento accanto a `licenza` nella voce
`litologia` di `src/limen/config/dati.yaml`, e seguire i punti 3 o 4 della
#495 (pacchetto rapido se è libera, fonte alternativa misurata se non lo è).

---

**Oggetto:** Carta geolitologica d'Italia 1:500.000 — chiarimento sulla licenza d'uso per un progetto open source

Gentili responsabili del Geoportale Nazionale,

scrivo per conto del progetto **Limen**, un sistema open source (licenza
EUPL-1.2, codice pubblico su https://github.com/agent-engineering-studio/limen)
che stima ogni ora il pericolo di frana, alluvione e incendio boschivo su una
griglia di celle da 1 km² del territorio italiano, usando solo dati pubblici.

Per le frane Limen usa la **Carta geolitologica d'Italia alla scala
1:500.000** pubblicata dal Geoportale Nazionale, scaricata dal servizio
`http://wms.pcn.minambiente.it/ogc?map=/ms_ogc/wfs/Carta_geolitologica.map`.
Dalla carta ricaviamo, per ogni cella, la classe litologica prevalente e un
peso numerico che entra nel calcolo della suscettibilità. Nella documentazione
del progetto e sulla mappa citiamo la fonte come «Ministero dell'Ambiente e
della Sicurezza Energetica, Geoportale Nazionale».

Abbiamo trovato due indicazioni che non riusciamo a conciliare:

- il servizio di download indica la licenza **Creative Commons Attribuzione
  4.0 (CC BY 4.0)**;
- le [note legali](https://gn.mase.gov.it/portale/note-legali) del portale
  parlano di un uso consentito «ai soli fini dei loro utilizzi istituzionali».

Prima di continuare a usare e ridistribuire dati derivati dalla carta,
vorremmo una conferma scritta su questi punti:

1. La Carta geolitologica d'Italia 1:500.000 scaricata dal servizio indicato è
   distribuita con licenza **CC BY 4.0 senza limiti di finalità**, cioè anche
   per usi non istituzionali?
2. È consentito **ridistribuire valori derivati** (la classe litologica e un
   peso numerico per ciascuna cella da 1 km²) dentro un pacchetto di dati
   aperti scaricabile da chiunque installi Limen?
3. È consentito l'uso da parte di **soggetti privati**, per esempio un
   integratore che installa e gestisce Limen per conto di un Comune o di
   un'altra amministrazione?
4. Qual è la **dicitura di attribuzione** esatta che dobbiamo riportare?

Se la carta non potesse essere usata in uno di questi modi, ci basta saperlo:
sostituiremo la fonte con un'alternativa a licenza aperta, dopo averla
misurata.

Ringraziamo per l'attenzione e per il lavoro di pubblicazione dei dati
geografici nazionali.

Cordiali saluti,

[Nome e cognome]
[Ruolo nel progetto Limen]
[Recapito per la risposta]
