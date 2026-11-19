-- Le classi che le corse previsionali per cella avevano dato a un giorno,
-- prima di un istante (`carico_repo.classi_previste`, #629): la previsione di
-- Limen da affiancare al bollettino di allerta emesso la vigilia.
--
-- $1 giorno:   il giorno-obiettivo, civile italiano come `valid` del bollettino
-- $2 prima_di: solo le corse partite prima di questo istante (l'emissione del bollettino)
-- $3 pericoli: i pericoli da leggere
--
-- Stessa definizione di `carico.sql` e `anticipo.sql`: una corsa che punta a
-- quel giorno, su una cella. Lo storico tiene le righe previsionali solo da
-- Moderato in su: una cella che qui non c'è era prevista sotto Moderato. Le
-- corse partono al più 72 ore prima del loro obiettivo, da cui il limite
-- inferiore su computed_at (le partizioni sono per giorno).
SELECT DISTINCT ra.cell_id, ra.hazard_type::text AS hazard, ra.class
FROM risk_assessments ra
WHERE ra.horizon LIKE '+%'
  AND ra.hazard_type::text = ANY($3::text[])
  AND ra.class IN ('Moderate', 'High', 'VeryHigh')
  AND ra.computed_at >= $1::date - interval '3 days'
  AND ra.computed_at < $2::timestamptz
  AND ((ra.computed_at
        + make_interval(hours => ltrim(rtrim(ra.horizon, 'h'), '+')::int))
       AT TIME ZONE 'Europe/Rome')::date = $1::date
