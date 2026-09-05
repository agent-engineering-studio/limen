-- Suolo impermeabilizzato per cella — issue #63.
--
-- Frazione media di superficie sigillata, da CLMS Imperviousness Density.
-- Amplifica il **solo** ramo pluviale del punteggio alluvione: il cemento non
-- fa crescere un fiume, fa scorrere la stessa pioggia invece di lasciarla
-- infiltrare, che è il meccanismo del flash flood urbano.
--
-- NULL = ignoto, e non è 0: scrivere zero su una cella che il mosaico non
-- copre affermerebbe che è tutta permeabile, sopprimendo l'amplificazione
-- proprio dove il dato manca.

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS imperviousness_norm DOUBLE PRECISION
        CHECK (imperviousness_norm IS NULL
               OR (imperviousness_norm >= 0 AND imperviousness_norm <= 1));

COMMENT ON COLUMN cell_static_factors.imperviousness_norm IS
    'Frazione di suolo impermeabilizzato in [0,1] (CLMS, #63). Amplifica solo '
    'il ramo pluviale. NULL finché LIMEN_IMPERVIOUSNESS_RASTER non è configurato.';
