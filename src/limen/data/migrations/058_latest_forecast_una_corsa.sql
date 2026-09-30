-- 058 — lo stato previsionale tiene **una** corsa, non due.
--
-- Il popolamento della 057 ha preso le ultime 36 ore di storico previsionale,
-- e dentro c'erano due corse: quella del 29 e quella del 30. Il writer di
-- allora cancellava le righe solo delle celle che riscriveva, quindi una
-- cella prevista Moderata il 29 e scesa sotto soglia il 30 restava nello
-- storico a dire la previsione del giorno prima — ed è finita qui.
--
-- L'effetto si vedeva nel grafico: su Genova il primo punto «previsto» cadeva
-- alle 02 del 30, cioè nel passato, perché era il +24 h di una corsa di ieri.
-- È la staleness che la 057 descriveva nel suo commento, ricopiata dal suo
-- stesso popolamento.
--
-- Si tiene l'ultima corsa per pericolo. Una corsa dura una dozzina di minuti
-- (02:00-02:13 misurato) e le corse sono a 24 ore l'una dall'altra, quindi
-- sei ore di margine separano le due senza ambiguità. Le celle che restano
-- senza riga sono quelle che la corsa di oggi ha visto sotto soglia: «previsto
-- sotto Moderato», che è ciò che la loro assenza vuol dire.
--
-- Da qui in avanti non si riaccumula: il writer ora cancella tutte le celle
-- valutate da ogni corsa, non solo quelle che tornano sopra soglia.

DELETE FROM latest_forecast lf
USING (
    SELECT hazard_type, max(run_at) AS ultima
    FROM latest_forecast
    GROUP BY hazard_type
) u
WHERE lf.hazard_type = u.hazard_type
  AND lf.run_at < u.ultima - interval '6 hours';
