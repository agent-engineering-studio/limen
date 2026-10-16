-- 078 — un ruolo per pg_tileserv che vede solo ciò che la mappa disegna (#269).
--
-- pg_tileserv pubblica da solo ogni tabella con una colonna geometrica che il
-- suo ruolo può leggere, e ogni funzione `(z, x, y, ...) -> bytea` che può
-- eseguire. Collegato come `limen` pubblicava trenta layer, fra cui
-- `sensor_devices` con la posizione esatta dei sensori dei cittadini, e
-- `grid_cells`, `raster_refs`, `osm_infrastructure`, `landslide_events`.
--
-- `limen_tiles` legge le viste delle tile e le tre tabelle degli overlay che
-- la SPA richiede (`RiskMap.tsx`, `DivergenceMap.tsx`), più `v_multi_hazard`,
-- che la SPA legge passando da `multi_hazard_at`: concederla non pubblica
-- nessun dato nuovo. Nient'altro. Le viste girano con i diritti del proprietario, quindi non serve concedere le
-- tabelle sotto. Le tre funzioni invece no: diventano SECURITY DEFINER, con
-- il search_path fissato, altrimenti servirebbe `SELECT` su `grid_cells` e
-- `latest_risk`, e pg_tileserv le pubblicherebbe. Nessuna costruisce SQL
-- dai parametri: `risk_at` e `multi_hazard_at` sono SQL statico,
-- `forecast_at` passa i suoi con `EXECUTE ... USING`. Un futuro `CREATE OR
-- REPLACE` di una di queste deve ripetere `SECURITY DEFINER SET search_path`:
-- senza, torna INVOKER e le tile rispondono «permission denied».
--
-- Il ruolo nasce senza password: la mette l'API all'avvio da
-- `DB__TILES_PASSWORD`, che sta nel `.env` e non nel repo. Una tabella nuova
-- non è concessa a nessuno finché una migrazione non lo dice: chiuso per
-- difetto, e `tests/integration/test_ruolo_tiles.py` fallisce se l'elenco
-- dei layer pubblicati cambia.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'limen_tiles') THEN
        CREATE ROLE limen_tiles LOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO limen_tiles;

GRANT SELECT ON
    public.v_risk_tiles,
    public.v_region_tiles,
    public.v_comune_tiles,
    public.v_multi_hazard,
    public.v_dpc_allerte_oggi,
    public.v_shadow_divergence_tiles,
    public.fire_perimeters,
    public.flood_events,
    public.flood_hazard_subdiv
TO limen_tiles;

ALTER FUNCTION public.risk_at(integer, integer, integer, integer, hazard_type)
    SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION public.multi_hazard_at(integer, integer, integer)
    SECURITY DEFINER SET search_path = public, pg_temp;
ALTER FUNCTION public.forecast_at(integer, integer, integer, integer, text)
    SECURITY DEFINER SET search_path = public, pg_temp;
