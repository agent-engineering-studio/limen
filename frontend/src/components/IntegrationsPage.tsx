// "Integrazioni" — pagina tecnica per sviluppatori / gateway agentici.
// Documenta i due modi di parlare con Limen da un altro agente: MCP (pull di
// dati / azioni operative) e A2A (interoperabilità JSON-RPC tra agent, con
// streaming e push). Contenuto statico — è documentazione, non dati live.

const MCP_SEND = `openclaw mcp set limen-ops \\
  '{"url":"http://127.0.0.1:8766/mcp","transport":"streamable-http"}'`;

const A2A_SEND = `POST /a2a
{
  "jsonrpc": "2.0", "id": "1", "method": "message/send",
  "params": {
    "message": {
      "role": "user", "messageId": "m1",
      "parts": [{ "kind": "data",
        "data": { "skill": "risk_summary", "params": { "aoi_id": "it-puglia" } } }]
    }
  }
}`;

const A2A_STREAM = `POST /a2a   method: "message/stream"   (stessi params)
→ text/event-stream:
  data: {"result":{"kind":"task","status":{"state":"submitted"}}}
  data: {"result":{"kind":"status-update","status":{"state":"working"}}}
  data: {"result":{"kind":"artifact-update","artifact":{...}}}
  data: {"result":{"kind":"status-update","status":{"state":"completed"},"final":true}}`;

interface Tool {
  name: string;
  desc: string;
}

const LIMEN_OPS: readonly Tool[] = [
  { name: "tool_risk_summary(aoi_id?)", desc: "Ultimo assessment per regione: celle per classe, punteggio max." },
  { name: "tool_top_risk_cells(limit?, aoi_id?)", desc: "Classifica delle celle a rischio più alto." },
  { name: "tool_cell_breakdown(cell_id)", desc: "Scomposizione S/M/E/F/H/K + briefing italiano di una cella." },
  { name: "tool_recent_alerts(threshold?, since_hours?, limit?)", desc: "Celle sopra soglia nella finestra recente." },
  { name: "tool_national_report()", desc: "Quadro nazionale aggregato + testo pronto in report_it." },
];

const LIMEN_OPS_ADMIN: readonly Tool[] = [
  { name: "tool_run_monitor(aoi_id, admin_token)", desc: "Lancia il workflow di monitoraggio una volta." },
  { name: "tool_build_report(admin_token)", desc: "Genera il report HTML statico on-demand (idempotente)." },
  { name: "tool_forecast_history(admin_token, aoi_ids?)", desc: "Persiste il trend di previsione (+24/48/72h) per i grafici UI." },
];

const ISPRA_GEO: readonly Tool[] = [
  { name: "tool_hazard_at(lat, lon)", desc: "Classe di pericolosità PAI + autorità + regione in un punto." },
  { name: "tool_iffi_query(...)", desc: "Frane del catalogo IFFI in un'area." },
  { name: "tool_pai_summary(region | bbox)", desc: "Distribuzione area/conteggio per classe PAI." },
  { name: "tool_dataset_status()", desc: "Stato dei dataset ISPRA caricati." },
  { name: "tool_refresh(dataset, admin_token)", desc: "Ricarica un dataset (admin, fail-closed)." },
];

const SKILLS: readonly Tool[] = [
  { name: "national_report", desc: "Sintesi nazionale (default se nessuna skill è indicata)." },
  { name: "risk_summary", desc: "Sintesi per regione (param aoi_id)." },
  { name: "top_risk_cells", desc: "Celle a rischio più alto (param limit, aoi_id)." },
  { name: "cell_breakdown", desc: "Scomposizione di una cella (param cell_id)." },
  { name: "recent_alerts", desc: "Allerte recenti (param threshold, since_hours, limit)." },
];

function ToolTable({ rows }: { rows: readonly Tool[] }): JSX.Element {
  return (
    <table className="int-table">
      <tbody>
        {rows.map((t) => (
          <tr key={t.name}>
            <td>
              <code>{t.name}</code>
            </td>
            <td>{t.desc}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function IntegrationsPage(): JSX.Element {
  return (
    <div className="explainer integrations" aria-label="Integrazioni per agenti">
      <article>
        <p className="exp-eyebrow">Per sviluppatori e agenti</p>
        <h2>Integrazioni: MCP &amp; A2A</h2>
        <p className="exp-lede">
          Limen si lascia interrogare da altri sistemi in due modi complementari:
          via <strong>MCP</strong> (un gateway agentico chiede dati e azioni) e via
          <strong> A2A</strong> (interoperabilità standard tra agent, con streaming
          e notifiche push). Entrambi sono di sola lettura sul punteggio: nessuna
          integrazione può alterare un valore di rischio.
        </p>

        <h3>MCP — chiedere dati e azioni a Limen</h3>
        <p>
          Il <a href="https://modelcontextprotocol.io" target="_blank" rel="noreferrer">Model
          Context Protocol</a> espone Limen come «strumenti» che un gateway (OpenClaw,
          Claude Desktop, …) può chiamare. Due server MCP:
        </p>
        <h4>
          <code>limen-ops</code> · <code>http://127.0.0.1:8766/mcp</code>
        </h4>
        <p className="exp-note">Strumenti di lettura (aperti):</p>
        <ToolTable rows={LIMEN_OPS} />
        <p className="exp-note">
          Strumenti di scrittura (gated su <code>MCP_ADMIN_TOKEN</code> — env non
          impostato ⇒ disabilitati):
        </p>
        <ToolTable rows={LIMEN_OPS_ADMIN} />
        <h4>
          <code>ispra-geo</code> · <code>http://127.0.0.1:8765/mcp</code> (profilo geodata)
        </h4>
        <p className="exp-note">Dati geografici ISPRA (PAI / IFFI). Attivo solo sul VPS:</p>
        <ToolTable rows={ISPRA_GEO} />
        <p>Registrazione in un gateway:</p>
        <pre>
          <code>{MCP_SEND}</code>
        </pre>

        <h3>A2A — interoperabilità tra agent</h3>
        <p>
          Il protocollo <a href="https://a2a-protocol.org" target="_blank" rel="noreferrer">
          Agent2Agent</a> permette ad agent di terze parti di scoprire e usare Limen in
          modo standard. La carta capacità (Agent Card) è pubblicata su:
        </p>
        <pre>
          <code>GET /.well-known/agent-card.json</code>
        </pre>
        <p>
          Dichiara <code>streaming: true</code> e <code>pushNotifications: true</code>, e
          le skill disponibili (le stesse query di <code>limen-ops</code>):
        </p>
        <ToolTable rows={SKILLS} />
        <p>
          L'endpoint JSON-RPC 2.0 è <code>POST /a2a</code>. Una skill si seleziona con un
          <code> DataPart</code> (o nei <code>metadata</code> del messaggio); senza nulla,
          il server risponde con il quadro nazionale:
        </p>
        <pre>
          <code>{A2A_SEND}</code>
        </pre>
        <p>
          Per aggiornamenti incrementali usa <code>message/stream</code> (Server-Sent
          Events, sequenza completa del task):
        </p>
        <pre>
          <code>{A2A_STREAM}</code>
        </pre>
        <p>
          Altri metodi: <code>tasks/get</code> e <code>tasks/cancel</code> (polling e
          annullamento), <code>tasks/pushNotificationConfig/set</code> per farsi notificare
          via webhook al termine del task.
        </p>

        <h3>Setup rapido</h3>
        <p>
          Lo script idempotente{" "}
          <a
            href="https://github.com/agent-engineering-studio/limen/blob/main/scripts/setup_openclaw.sh"
            target="_blank"
            rel="noreferrer"
          >
            scripts/setup_openclaw.sh
          </a>{" "}
          registra entrambi gli MCP, abilita gli hook di notifica e stampa l'URL della
          Agent Card. Guida completa e troubleshooting:{" "}
          <a
            href="https://github.com/agent-engineering-studio/limen/blob/main/docs/openclaw.md"
            target="_blank"
            rel="noreferrer"
          >
            docs/openclaw.md
          </a>
          .
        </p>
        <p className="exp-note">
          Sicurezza: gli strumenti di lettura e le skill A2A non alterano mai i punteggi.
          Le azioni di scrittura richiedono <code>MCP_ADMIN_TOKEN</code> (fail-closed). Gli
          alert push sono testo deterministico, senza LLM nel percorso.
        </p>
      </article>
    </div>
  );
}

export default IntegrationsPage;
