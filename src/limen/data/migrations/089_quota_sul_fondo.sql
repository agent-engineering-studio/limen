-- #469: quanto una cella sta sopra il fondo valle, in metri.
--
-- La quota media della cella meno la quota più bassa fra le celle della stessa
-- regione entro tre righe e tre colonne (~3 km). La riempie il passo
-- «quota_sul_fondo» del bootstrap statico, dalla quota del DTM già caricata;
-- NULL = DTM assente, cioè ignoto, che il motore alluvione non usa.
--
-- Serve a modulare la classe idraulica: dentro le aree P3 le celle allagate
-- stanno in mediana 4 m sopra il fondo, quelle rimaste asciutte 15 m (misura
-- del 2026-11-08 sugli eventi Copernicus EMS, issue #469).

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS quota_sul_fondo_m double precision;
