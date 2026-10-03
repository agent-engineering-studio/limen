import { useEffect, useState } from "react";

import type { ForecastSchedule } from "../types";
import { defaultApiClient } from "./api-client";

/** Gli orari della previsione: l'ultima corsa per pericolo e la prossima.
 *
 *  Un hook e non una prop: lo leggono la sezione della previsione e la lista
 *  dei comuni, che stanno in due rami diversi della colonna. `null` finché
 *  non risponde e se non risponde — nessuno dei due ne ha bisogno per
 *  disegnarsi. */
export function useForecastSchedule(): ForecastSchedule | null {
  const [schedule, setSchedule] = useState<ForecastSchedule | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    defaultApiClient
      .getForecastSchedule(ctrl.signal)
      .then(setSchedule)
      .catch(() => {
        if (!ctrl.signal.aborted) setSchedule(null);
      });
    return () => ctrl.abort();
  }, []);
  return schedule;
}
