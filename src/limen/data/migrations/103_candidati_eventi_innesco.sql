-- 103 — che cosa ha mosso la frana, quando la stampa lo dice.
--
-- Una soglia di pioggia si verifica sulle frane da pioggia: una frana di un
-- cantiere o di una scossa, contata come mancata previsione, abbassa una
-- misura che non la riguarda. L'estrattore della raccolta (#347) scrive qui
-- l'innesco solo se un titolo lo dice; `ignoto` è la regola, non l'eccezione,
-- perché legge i titoli e non gli articoli. Alluvioni e incendi restano
-- `ignoto`.
--
-- Solo una colonna in più su `candidati_eventi`: `verifiche_eventi` e i
-- backtest non la leggono ancora.

ALTER TABLE candidati_eventi
    ADD COLUMN IF NOT EXISTS innesco text NOT NULL DEFAULT 'ignoto'
        CHECK (innesco IN ('pioggia', 'sisma', 'lavori', 'altro', 'ignoto'));

COMMENT ON COLUMN candidati_eventi.innesco IS
    'Che cosa ha mosso la frana secondo i titoli; ignoto se nessuno lo dice.';
