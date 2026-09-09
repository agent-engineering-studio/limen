"""Post-fire amplification window (§2.4) e severità del bruciato (#67).

A burnt slope is hydrologically distinct for ~2 years after a fire:
infiltration drops, runoff and shallow-instability risk increases.
We model the amplification factor as a Gaussian bell centred at
``peak_months`` and zero outside ``[0, window_months_max]``:

    F(m) = exp(−((m − peak_months)² / curve_denominator))    if 0 ≤ m ≤ window_max
         = 0                                                 otherwise

**La severità modula l'ampiezza, non la forma.** Un incendio di chioma severo
e una bruciatura di stoppie non lasciano il versante nello stesso stato, ma il
decorso temporale dell'idrofobicità è lo stesso: cambia quanto, non quando.
Quindi la severità entra come fattore moltiplicativo sull'ampiezza e la
campana resta dov'era.

    F(m, sev) = F(m) · (severity_floor + (1 − severity_floor) · sev)

Il moltiplicatore è **≤ 1 per costruzione**: la severità può solo attenuare
un allarme, mai inventarne uno. Con ``severity=None`` — nessuna misura
disponibile — o ``severity_floor = 1`` il risultato è identico a prima, quindi
nessun ricalibro è obbligato.

La severità viene dalla densità di potenza radiativa FIRMS, non dal dNBR: il
dNBR sarebbe la misura giusta ma il suo endpoint Copernicus richiede una
richiesta manuale, e ``EffisClient.fetch_dnbr`` è rimasto uno stub. La firma
accetta un numero in [0,1] e non si accorge di dove venga, quindi il dNBR
potrà sostituirlo senza toccare il motore.

Funzioni pure di ``months_since_fire``, della severità e di
:class:`PostFireBlock`.
"""

from __future__ import annotations

import math

from limen.core.scoring.regional_thresholds import PostFireBlock


def frp_severity(
    frp_density_mw_per_ha: float | None,
    *,
    post_fire: PostFireBlock,
) -> float | None:
    """Severità in [0, 1] dalla densità di FRP. ``None`` resta ``None``.

    Rampa lineare fra ``frp_floor_mw_per_ha`` e ``frp_saturation_mw_per_ha``,
    ancorati al decimo e al novantesimo percentile misurati sui perimetri
    EFFIS italiani.

    Si prende la **densità** e non la somma di FRP: misurato su 2.419
    perimetri, la somma correla con l'area a 0,63 e la densità a 0,26, quindi
    la somma è in gran parte un indicatore di dimensione del rogo. Usarla come
    severità direbbe che un incendio grande è per definizione severo.

    ``None`` non diventa 0: "non misurato" e "bruciato debolmente" sono fatti
    diversi, e schiacciarli farebbe attenuare l'allarme ogni volta che un
    perimetro non ha hotspot dentro.
    """
    if frp_density_mw_per_ha is None:
        return None
    lo = post_fire.frp_floor_mw_per_ha
    hi = post_fire.frp_saturation_mw_per_ha
    if hi <= lo:
        raise ValueError(
            f"post_fire.frp_saturation_mw_per_ha must exceed frp_floor_mw_per_ha, got {hi} <= {lo}"
        )
    if frp_density_mw_per_ha <= lo:
        return 0.0
    if frp_density_mw_per_ha >= hi:
        return 1.0
    return (frp_density_mw_per_ha - lo) / (hi - lo)


def severity_multiplier(severity: float | None, *, post_fire: PostFireBlock) -> float:
    """Il fattore per cui la campana viene moltiplicata, in [floor, 1].

    Separato da :func:`post_fire_factor` perché finisce nel breakdown: un
    operatore che vede un fattore F più basso del previsto deve poter leggere
    quanto la severità l'ha attenuato, senza ricalcolare niente.
    """
    if severity is None:
        return 1.0
    floor = post_fire.severity_floor
    clamped = min(max(severity, 0.0), 1.0)
    return floor + (1.0 - floor) * clamped


def post_fire_factor(
    months_since_fire: float | None,
    *,
    post_fire: PostFireBlock,
    severity: float | None = None,
) -> float:
    """Return ``F`` in [0, 1]. ``None`` (no recent fire) → 0.

    ``severity=None`` ⇒ identico al comportamento precedente alla #67.
    """
    if months_since_fire is None:
        return 0.0
    if months_since_fire < 0 or months_since_fire > post_fire.window_months_max:
        return 0.0
    if post_fire.curve_denominator <= 0:
        raise ValueError(
            f"post_fire.curve_denominator must be > 0, got {post_fire.curve_denominator}"
        )
    bell = math.exp(
        -((months_since_fire - post_fire.peak_months) ** 2) / post_fire.curve_denominator
    )
    return bell * severity_multiplier(severity, post_fire=post_fire)


__all__ = ["frp_severity", "post_fire_factor", "severity_multiplier"]
