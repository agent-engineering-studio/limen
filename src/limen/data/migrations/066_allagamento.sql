-- 066 — il pericolo «flood» si chiama Allagamento.
--
-- «Alluvione · molto alto» accanto a un bollettino senza allerta spaventava
-- più di quanto i numeri dicano: il motore stima acqua che si accumula dove
-- la zona è allagabile — pioggia forte su suolo impermeabile o portata dei
-- fiumi sopra la loro piena ordinaria — non un'alluvione in corso. Cambia
-- solo il nome che la SPA e le API mostrano; `hazard_type` resta `flood`.

UPDATE hazards SET label_it = 'Allagamento' WHERE hazard = 'flood';
