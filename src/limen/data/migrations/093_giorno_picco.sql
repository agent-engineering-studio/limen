-- 093 — Il giorno del picco previsto di portata, accanto al picco (#522).
--
-- `glofas_previsione.picco` è il massimo dei 7 giorni della corsa di
-- controllo GloFAS. Il 10 novembre 2026, sul Serchio, l'etichetta «sopra la
-- piena da 20 anni» si leggeva come una cosa di adesso, e il picco era
-- previsto il 14: senza il giorno, chi legge il riquadro non lo può sapere.
--
-- NULL = corsa salvata prima di questa colonna.

ALTER TABLE glofas_previsione ADD COLUMN IF NOT EXISTS giorno_picco date;
