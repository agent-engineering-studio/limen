-- 101_crop_burning_share.sql
--
-- Quanto coltivo c'è sotto il fuoco di una cella (#714): la quota media di
-- coltivi ESA WorldCover (classe 40) attorno alle rilevazioni VIIRS di
-- vegetazione (`detection_type = 0`) dei giorni-incendio della cella, da 0 a
-- 1. La calcola `firms_client.cell_stats` nel passo `crop_burning` del
-- bootstrap statico.
--
-- Serve alla domanda della #714 sul Nord: i roghi agricoli sono un segnale
-- oltre l'FWI? Il bootstrap la conta fino a oggi: per misurarla con
-- `limen misura` va ricalcolata fermandosi alla fine del periodo di stima,
-- o una cella bruciata nel periodo di verifica la avrebbe per quell'incendio.
--
-- NULL non è zero. NULL è «non misurato»: una cella senza giorni-incendio
-- (non c'è terra *sotto un fuoco* da descrivere) o senza le tile WorldCover
-- nell'init. Lo zero è un fuoco su terra senza coltivi.
--
-- WorldCover chiama prato il pascolo e il maggese: sugli incendi EFFIS su
-- terra agricola al 90 % la quota esce tra 0,58 e 0,86, sui boschivi tra 0 e
-- 0,004 (benchmark di firms-client 0.7.0). È un numero continuo, non
-- un'etichetta «rogo agricolo».

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS crop_burning_share double precision;

COMMENT ON COLUMN cell_static_factors.crop_burning_share IS
    'Quota media di coltivi WorldCover sotto le rilevazioni VIIRS di vegetazione dei giorni-incendio (0-1); NULL = non misurato';
