-- Acqua e umido temporanei per cella — issue #420.
--
-- Quota della cella in cui l'HRL WaterWetness 2018 di Copernicus (2009-2015)
-- ha visto acqua o umido temporanei (classi 2 e 4) sui pixel classificati.
-- Modula la suscettibilità alluvionale delle sole celle dentro il mosaico
-- idraulico: fra celle della stessa classe ISPRA, quelle che l'acqua la
-- tengono davvero si sono allagate tre volte più spesso (EMS 2023-2026).
--
-- NULL = ignoto (raster non configurato, o troppi pixel non classificati),
-- e non è 0: zero direbbe che l'acqua lì non si è mai vista.

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS water_wetness_temp DOUBLE PRECISION
        CHECK (water_wetness_temp IS NULL
               OR (water_wetness_temp >= 0 AND water_wetness_temp <= 1));

COMMENT ON COLUMN cell_static_factors.water_wetness_temp IS
    'Quota di acqua e umido temporanei in [0,1] (HRL WaterWetness 2018, #420). '
    'Modula la suscettibilità alluvione delle celle mappate. NULL finché '
    'LIMEN_WATER_WETNESS_RASTER non è configurato.';
