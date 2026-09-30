-- 056 — «StalettÃ¬» era «Stalettì».
--
-- 147 comuni su 7901 hanno il nome doppiamente codificato: i byte UTF-8 di
-- «ì» (C3 AC) letti come due caratteri LATIN1 e ri-codificati in UTF-8.
-- Succede quando uno shapefile ISTAT — che è in ISO-8859-1 — viene caricato
-- dichiarando UTF-8, e qui è successo a monte, nel PostGIS di GeoServer da
-- cui `limen seed-comuni` legge i confini. Da lì è arrivato intatto fino
-- alla colonna dei comuni, dove un cittadino di Cefalù legge «CefalÃ¹».
--
-- La cura è il giro inverso: ri-codificare in LATIN1 e rileggere come UTF-8.
-- Sui nomi già corretti fallisce — «ì» in LATIN1 è il byte EC, che da solo
-- non è UTF-8 valido — quindi la funzione restituisce l'originale e
-- l'operazione è ripetibile senza danno. Il filtro su `[ÃÂ]` la limita ai
-- nomi sospetti: è una cintura in più, non la sicurezza.
--
-- Il seeder fa la stessa cosa in Python quando legge, così un re-seed dalla
-- sorgente ancora rotta non riporta indietro i 147 nomi.

CREATE OR REPLACE FUNCTION _demojibake(t text) RETURNS text AS $$
BEGIN
    RETURN convert_from(convert_to(t, 'LATIN1'), 'UTF8');
EXCEPTION WHEN others THEN
    -- Non era doppiamente codificato: si tiene com'è.
    RETURN t;
END
$$ LANGUAGE plpgsql IMMUTABLE;

UPDATE comuni
   SET name = _demojibake(name)
 WHERE name ~ '[ÃÂ]';

DROP FUNCTION _demojibake(text);

-- Il rollup porta il nome, quindi va rifatto o la colonna continua a
-- mostrare quello vecchio finché non passa uno sweep.
REFRESH MATERIALIZED VIEW mv_comune_risk;
