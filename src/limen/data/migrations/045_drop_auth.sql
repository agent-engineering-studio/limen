-- 045_drop_auth.sql
--
-- Rimozione dell'autenticazione utente (epic #69).
--
-- Limen è una dashboard cartografica **pubblica**: ML e AI girano in batch
-- notturni e orari senza identità utente, non esiste chat, non esistono dati
-- per-utente. L'autenticazione non comprava nessuna funzione, e teneva dati
-- personali di cittadini custoditi da una PA senza una ragione che lo
-- giustificasse.
--
-- **La 025 non si tocca**: è applicata e tracciata con checksum SHA-256, e
-- l'invariante del progetto vieta di modificare una migrazione applicata anche
-- solo nei commenti. Su un database nuovo la sequenza 025 → 045 crea e poi
-- distrugge le tabelle: è lavoro sprecato di qualche millisecondo, ed è il
-- prezzo giusto per una storia delle migrazioni che resta verificabile.
--
-- Ordine figli → padre: `sessions` e `auth_codes` hanno chiavi esterne verso
-- `users`, quindi droppare prima il padre richiederebbe un CASCADE — che
-- funzionerebbe, ma nasconderebbe nel silenzio l'eventuale dipendenza di una
-- tabella che non conosciamo.
--
-- `citext` **resta**: l'estensione l'ha introdotta la 025 per la colonna
-- email, ma è a livello di database e un'altra migrazione potrebbe averne
-- bisogno. Rimuoverla per pulizia sarebbe la fretta a decidere.
--
-- Se un giorno nascerà un'area per operatori di Regione o Protezione Civile —
-- presa visione delle allerte, destinatari configurabili, soglie per comune —
-- il login si riapre per loro, e a quel punto SPID/CIE avrà senso. Il lavoro
-- della #49 resta nella storia git e si recupera. Reintrodurlo oggi sarebbe
-- future-proofing.

DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS auth_codes;
DROP TABLE IF EXISTS users;
