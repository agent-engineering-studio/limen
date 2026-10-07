// Un guasto in una pagina resta in quella pagina.
//
// Senza un confine, un'eccezione durante il rendering o in un effetto smonta
// l'intera applicazione: il 7 ottobre 2026 «Regioni da monitorare» lanciava
// un errore della mappa e restava solo lo sfondo nero, senza intestazione né
// menu per tornare indietro.

import { Component } from "react";
import type { ErrorInfo, JSX, ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Cambiando chiave il confine si azzera: serve quando si cambia pagina. */
  chiave: string;
}

interface Stato {
  errore: Error | null;
  chiave: string;
}

export default class ErroreLocale extends Component<Props, Stato> {
  override state: Stato = { errore: null, chiave: this.props.chiave };

  static getDerivedStateFromError(errore: Error): Partial<Stato> {
    return { errore };
  }

  static getDerivedStateFromProps(props: Props, stato: Stato): Partial<Stato> | null {
    return props.chiave !== stato.chiave ? { errore: null, chiave: props.chiave } : null;
  }

  override componentDidCatch(errore: Error, info: ErrorInfo): void {
    console.error("pagina", errore, info.componentStack);
  }

  override render(): ReactNode {
    if (this.state.errore) return <Avviso />;
    return this.props.children;
  }
}

function Avviso(): JSX.Element {
  return (
    <div className="explainer" role="alert">
      <h2>Questa pagina non si è caricata</h2>
      <p>
        Le altre sezioni funzionano: torna alla <a href="#/dashboard">mappa</a> o ricarica la
        pagina tra poco.
      </p>
    </div>
  );
}
