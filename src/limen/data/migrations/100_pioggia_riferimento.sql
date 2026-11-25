-- La pioggia di riferimento per cella — #676, #656.
--
-- L'innesco frana `cumulata` divide la pioggia delle ultime 24 ore per il
-- q999 della stessa cumulata al nodo ERA5 (0,1°) più vicino alla cella, dagli
-- anni 1995-2007 (`limen clima-pioggia`). Una soglia in millimetri non vale in
-- tutte le regioni, divisa per il riferimento del suo nodo sì: sulle dodici
-- finestre della #122 coglie il 74 % dei comuni con una frana con il 10 % dei
-- comuni-giorno in allerta, contro il 51 % di Caine.
--
-- NULL = nessun riferimento (nodo in mare, o comando non ancora eseguito): la
-- cella resta su Caine e il cancello d'innesco non la chiude.

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS pioggia_riferimento_mm DOUBLE PRECISION
        CHECK (pioggia_riferimento_mm IS NULL OR pioggia_riferimento_mm > 0);

COMMENT ON COLUMN cell_static_factors.pioggia_riferimento_mm IS
    'q999 della cumulata 24 h al nodo ERA5 più vicino, 1995-2007 (limen clima-pioggia, #676). '
    'Il metro dell''innesco cumulata di landslide.yaml. NULL = nessun riferimento.';
