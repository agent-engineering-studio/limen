import type { PanelFailure } from "../lib/panel-state";

// I tre stati che un pannello può avere quando non ha numeri da mostrare, e
// che devono *sembrare* diversi: sta arrivando, non c'è niente da dire,
// qualcosa è rotto.
//
// Nessuno dei tre usa la scala di colori del rischio. Il giallo-rosso di
// quella scala significa «pericolo»: riusarlo per un guasto di rete
// vorrebbe dire dire una bugia con un colore.

export function PanelLoading({ label }: { label: string }): JSX.Element {
  return (
    <div className="panel-state is-loading" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <span className="skeleton-bar" style={{ width: "72%" }} aria-hidden />
      <span className="skeleton-bar" style={{ width: "88%" }} aria-hidden />
      <span className="skeleton-bar" style={{ width: "54%" }} aria-hidden />
    </div>
  );
}

/**
 * Niente da segnalare. È una notizia, non un errore: tono neutro, nessuna
 * icona d'allarme, nessun rosso.
 */
export function PanelEmpty({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}): JSX.Element {
  return (
    <div className="panel-state is-empty">
      <p className="panel-state-title">{title}</p>
      {detail ? <p className="panel-state-detail">{detail}</p> : null}
    </div>
  );
}

export function PanelDegraded({
  failure,
  onRetry,
}: {
  failure: PanelFailure;
  onRetry?: () => void;
}): JSX.Element {
  return (
    <div className="panel-state is-degraded" role="alert">
      <p className="panel-state-title">{failure.title}</p>
      <p className="panel-state-detail">{failure.detail}</p>
      {failure.retryable && onRetry ? (
        <button type="button" className="panel-retry" onClick={onRetry}>
          Riprova
        </button>
      ) : null}
    </div>
  );
}
