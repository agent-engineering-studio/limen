-- 075 — livello di fiducia dei dispositivi in situ (#251, epic #247).
--
-- Il percorso V1.5 non sapeva chi aveva misurato: la misura di qualunque
-- dispositivo legato a una cella sostituiva il modello in M, e
-- l'accelerazione di un estensimetro faceva scattare `hard_escalation`, che
-- scavalca la soglia delle allerte. Un pluviometro intasato che segna zero
-- abbassava il punteggio; un sensore urtato mandava un'allerta. Con i
-- dispositivi dei cittadini in arrivo, questo va chiuso prima.
--
--   0  osservatore    — chiunque dopo la registrazione: archivio e verifiche
--   1  verificato     — promosso dopo l'accordo con il radar; potrà solo
--                       alzare la pioggia, con quorum e tetto (#258)
--   2  istituzionale  — enti, Protezione civile: l'unico che entra nello
--                       scoring e nelle allerte
--
-- I dispositivi già registrati sono istituzionali: l'ADD COLUMN li riempie
-- con 2, e la migrazione non cambia nessun punteggio esistente. Da lì in poi
-- il default è 0: un INSERT che dimentica il livello deve lasciare il
-- dispositivo fuori dallo scoring, non dentro. È il rollup orario a
-- leggere solo il livello 2; le osservazioni grezze di tutti restano in
-- `sensor_observations`.
--
-- Chi ha registrato il dispositivo arriva con la registrazione (#253), come
-- chiave verso la sua tabella: una colonna `registrante_id` senza quella
-- tabella non avrebbe niente a cui riferirsi.

ALTER TABLE sensor_devices
    ADD COLUMN IF NOT EXISTS livello smallint NOT NULL DEFAULT 2
        CONSTRAINT sensor_devices_livello_chk CHECK (livello IN (0, 1, 2));

ALTER TABLE sensor_devices ALTER COLUMN livello SET DEFAULT 0;
