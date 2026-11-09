"""Il gate di promozione dello sfidante ML, in due tempi (#483).

La validazione incrociata spaziale dice se il modello **discrimina** (AUC-PR,
Brier, meglio della V1 sulla stessa partizione), ma gira su un campione
caso-controllo: un positivo ogni sei righe, quindi hit rate e falsi allarmi
misurati lì sono ottimisti per costruzione, e il campione non sa a che ora è
arrivato l'evento, quindi l'anticipo non si può misurare affatto. Fino alla
#483 il gate li prendeva comunque da lì, con l'anticipo fisso a zero contro
una soglia di 18 ore: nessun modello poteva passarlo.

Hit rate, falsi allarmi e anticipo vengono ora dal **backtest** (`limen
backtest` con `LIMEN_BACKTEST_SFIDANTE`): stessa finestra, stessi eventi e
stessa pioggia della V1, con lo sfidante in allerta allo stesso tasso di
celle-ora della V1, così un modello non vince accendendo di più.

Promuovere resta un comando dell'operatore: qui si scrive solo il tag.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from limen.config.settings import Settings
from limen.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EsitoBacktest:
    """Quello che il backtest dice di un motore su una o più AOI."""

    eventi: int
    colti: int
    falsi_allarmi: int
    anticipo_medio_ore: float
    celle: int
    celle_ore: int
    celle_ore_in_allerta: int

    @property
    def hit_rate(self) -> float:
        return self.colti / self.eventi if self.eventi else 0.0

    @property
    def far(self) -> float:
        allerte = self.colti + self.falsi_allarmi
        return self.falsi_allarmi / allerte if allerte else 0.0

    @property
    def quota_allertate(self) -> float:
        return self.celle_ore_in_allerta / self.celle_ore if self.celle_ore else 0.0

    @property
    def tasso_base(self) -> float:
        """Quota di celle con un evento: un hit rate si legge solo accanto a questa."""
        return self.eventi / self.celle if self.celle else 0.0


def unisci(esiti: Iterable[EsitoBacktest]) -> EsitoBacktest:
    """Somma più AOI; l'anticipo è la media pesata sugli eventi colti."""
    lista = list(esiti)
    colti = sum(e.colti for e in lista)
    return EsitoBacktest(
        eventi=sum(e.eventi for e in lista),
        colti=colti,
        falsi_allarmi=sum(e.falsi_allarmi for e in lista),
        anticipo_medio_ore=(
            sum(e.anticipo_medio_ore * e.colti for e in lista) / colti if colti else 0.0
        ),
        celle=sum(e.celle for e in lista),
        celle_ore=sum(e.celle_ore for e in lista),
        celle_ore_in_allerta=sum(e.celle_ore_in_allerta for e in lista),
    )


def gate_validazione(
    settings: Settings, *, ml_auc_pr: float, ml_brier: float, baseline_auc_pr: float
) -> bool:
    """La metà del gate che la validazione incrociata può decidere."""
    g = settings.scoring
    return (
        ml_auc_pr >= g.promotion_auc_pr_min
        and ml_brier <= g.promotion_brier_max
        and ml_auc_pr > baseline_auc_pr
    )


def gate_backtest(settings: Settings, esito: EsitoBacktest, campione: EsitoBacktest) -> bool:
    """La metà che solo il backtest può decidere: eventi colti, allarmi a vuoto,
    anticipo, e a parità di allerte almeno gli eventi che coglie la V1."""
    g = settings.scoring
    return (
        esito.eventi > 0
        and esito.quota_allertate <= campione.quota_allertate
        and esito.colti >= campione.colti
        and esito.hit_rate >= g.promotion_hit_rate_min
        and esito.far <= g.promotion_far_max
        and esito.anticipo_medio_ore >= g.promotion_lead_time_hours_min
    )


def registra_esito(
    *,
    finestra: str,
    aoi: list[str],
    tracking_uri: str,
    registered_model: str,
    versione: str,
    sfidante: EsitoBacktest,
    campione: EsitoBacktest,
    settings: Settings,
) -> bool:
    """Scrive l'esito del backtest sul run MLflow della versione e decide ``promoted``.

    ``promoted`` è vero solo se la validazione (tag ``gate_validazione``
    scritto da ``limen train``) **e** il backtest passano. Non sposta lo stage.
    """
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri)
    mv = client.get_model_version(registered_model, versione)
    run_id = mv.run_id
    if run_id is None:
        # Una versione registrata a mano, senza run: non c'è un `gate_validazione` da leggere.
        raise ValueError(f"{registered_model} v{versione} non ha un run MLflow")
    run = client.get_run(run_id)
    validazione = run.data.tags.get("gate_validazione") == "True"
    backtest = gate_backtest(settings, sfidante, campione)
    promosso = validazione and backtest
    for nome, valore in (
        ("backtest_hit_rate", sfidante.hit_rate),
        ("backtest_far", sfidante.far),
        ("backtest_anticipo_ore", sfidante.anticipo_medio_ore),
        ("backtest_quota_allertate", sfidante.quota_allertate),
        ("backtest_tasso_base", sfidante.tasso_base),
        ("backtest_v1_hit_rate", campione.hit_rate),
        ("backtest_v1_far", campione.far),
        ("backtest_v1_anticipo_ore", campione.anticipo_medio_ore),
    ):
        client.log_metric(run_id, nome, valore)
    # Da dove viene il verdetto: una finestra di due eventi non è un esame.
    client.set_tag(run_id, "backtest_finestra", finestra)
    client.set_tag(run_id, "backtest_aoi", ",".join(aoi))
    client.set_tag(run_id, "backtest_eventi", str(sfidante.eventi))
    client.set_tag(run_id, "gate_backtest", str(backtest))
    client.set_tag(run_id, "promoted", str(promosso))
    client.set_model_version_tag(registered_model, versione, "promoted", str(promosso))
    log.info(
        "promozione.esito",
        modello=registered_model,
        versione=versione,
        validazione=validazione,
        backtest=backtest,
        promoted=promosso,
        hit_rate=round(sfidante.hit_rate, 4),
        far=round(sfidante.far, 4),
        anticipo_ore=round(sfidante.anticipo_medio_ore, 1),
        tasso_base=round(sfidante.tasso_base, 6),
    )
    return promosso
