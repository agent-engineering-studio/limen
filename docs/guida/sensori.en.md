# Sensors and MQTT

> ⚠️ **Work in progress — coming in the next releases.** The sensor network
> does not accept measurements yet: the broker exists, but the protocol,
> registration and kits are under development and may change. Do not build
> or install a sensor expecting Limen to read it already.

**Limen uses MQTT in two opposite directions, with two separate brokers.**
The alert broker sends warnings out to the systems of whoever receives them.
The sensor broker brings measurements in from the territory: rain gauges,
water-level gauges, soil-moisture probes, built also by citizens, schools
and associations with an ESP32 or a Raspberry Pi. The two brokers are never
the same process, because their security needs are opposite.

The citizen sensor network is **under construction** (epic
[#247](https://github.com/agent-engineering-studio/limen/issues/247)). This
page describes what already exists, what is coming and, above all, which
rules apply to whoever installs a sensor.

## Two brokers, two jobs

| | Alert broker | Sensor broker |
|---|---|---|
| Container | `limen-mosquitto` | `limen-mosquitto-sensori` |
| Direction | Limen → out | out → Limen |
| Who publishes | Limen only | each device, on its own topic only |
| Authentication | none: reachable only from the server | one X.509 certificate per device (mTLS) |
| Exposure | never, loopback only | port 8883, through nginx |
| Topics | `limen/alerts` | `limen/v2/<id>/obs`, `limen/v2/<id>/status` |

Keeping them apart is not a formality. The alert broker accepts anonymous
connections because nobody outside the server can reach it; the sensor
broker sits on the Internet and accepts nobody without a certificate.
Merging them would mean weakening the first or breaking the second.

## The alert broker

**When an hourly sweep finds cells above threshold, Limen publishes a
warning on the `limen/alerts` topic.** It is one of the four push channels,
together with Telegram, email and webhook. It is switched on by listing
`mqtt` in `NOTIFICATIONS__ENABLED_CHANNELS` and setting the
`NOTIFICATIONS__MQTT__*` variables (host, port, topic, QoS, optional
credentials and TLS).

Each warning is a JSON message, published with QoS 1 by opening a
connection, publishing and closing it: warnings are rare, and an always-open
session is not worth its complexity. The content:

| Field | What it holds |
|---|---|
| `aoi_id`, `hazard_type` | the area and the hazard (landslide, flood, wildfire) |
| `max_level`, `max_score` | the highest class and score among the alerted cells |
| `cells` | the cells: id, score, class, priority, municipality, map link |
| `aggregates` | the per-municipality summary |
| `summary_it` | the Italian text of the warning |
| `cascade` | the active cross-hazard cascades, if any |
| `map_url`, `pipeline_version`, `dispatched_at` | link, version, send time |

The `summary_it` text is built deterministically from the engine's
numbers: **there is no language model in the alert path**, so a warning
cannot contain an invented figure. Warnings go through the same
deduplication and the same limits as the other channels: a cell already
warned about inside the window is not repeated.

The broker runs on Limen's server and listens on loopback only. To receive
the warnings in another system, use an MQTT bridge from your own broker, or
the webhook channel described in
[Integrations](#/integrazioni/notifiche-push).

## The sensor broker

**A dedicated Mosquitto, reachable from the Internet on port 8883, that
accepts only devices holding a certificate signed by Limen's sensor CA.** It
is hosted on Limen's own server, not on a cloud: it costs almost nothing and
speaks standard MQTT, so a device will not have to change anything if one
day the broker moves.

How it is defended:

- **mutual TLS authentication**: the device checks the server and the server
checks the device. A client without a certificate does not even complete the
connection;
- **identity is the certificate**: the device name comes from the CN field of
its certificate, never from a field of the message, so copying someone
else's id is useless;
- **each device writes only to its own topic**: a device publishes on
`limen/v2/<its id>/…` and cannot read anything, not even its own data;
- **immediate revocation**: a compromised, stolen or broken device is revoked
on its own, without touching the others;
- **port behind nginx**: the container listens on the server only; the public
port belongs to nginx, which forwards the encrypted traffic without
decrypting it and limits the number of connections per address.

Before every go-live an automatic check verifies that the broker really
refuses what it must refuse:

| Test | Expected outcome |
|---|---|
| client without a certificate | refused |
| certificate signed by another CA | refused |
| valid device on its own topic | delivered to Limen |
| valid device on someone else's topic | dropped |
| revoked device | refused |
| revocation list close to expiry | flagged |

## The v2 protocol

**Few fields, fixed units, identity in the certificate.** The protocol is
being defined ([#252](https://github.com/agent-engineering-studio/limen/issues/252)):
what follows is the direction, not a contract yet.

Two topics per device:

```
limen/v2/<id>/obs       the measurements
limen/v2/<id>/status    alive or not (MQTT client last will)
```

The device **does not declare where it is**: Limen records its position,
region and grid cell when it approves the device. One less datum to verify,
and a sensor that has been moved gets noticed.

The message follows SenML (RFC 8428), the standard format for sensor
measurements: JSON over Wi-Fi or mobile networks, CBOR where every byte
counts, as on LoRaWAN.

```json
[
  {"bn": "pluvio-matera-01/", "bt": 1792065600, "n": "rainfall", "u": "mm", "v": 0.4},
  {"n": "seq", "v": 18342}
]
```

The quantities and their units:

| Quantity | Unit | For which hazard |
|---|---|---|
| `rainfall` | mm | landslide, flood |
| `soil_moisture` | m³/m³ | landslide |
| `water_level` | m | flood (coming) |
| `air_temperature`, `relative_humidity`, `wind_speed` | °C, %, km/h | wildfire (coming) |

Two rules apply to every message. Time is always UTC, taken from NTP. The
sequence number always grows: a device that loses its network keeps its
measurements and sends them again when it is back, and Limen accepts them
marked **late**. They do not enter the forecast for the hour, but they stay
in the archive and in the verifications: they are often the hours of the
storm, the ones that matter most.

## How a device gets its identity

**The private key is born in the device and never leaves it.** The device
generates its key pair on the P-256 curve and sends Limen only a signing
request (CSR) carrying its id. Limen signs it with the sensor CA and returns
the certificate. Together with it, the device receives the CA certificate,
the only one it will trust as a server.

This needs hardware that can handle TLS and elliptic-curve keys: an ESP32, a
Raspberry Pi Pico W or a Raspberry Pi. An Arduino Uno is not enough. The
most robust way to hold the key is a secure element such as the ATECC608,
which costs about one euro and does not let the key be extracted; the
alternative is the ESP32's secure boot and encrypted flash.

Registration will not need an account: a form, an email, and the approval
of whoever runs Limen
([#253](https://github.com/agent-engineering-studio/limen/issues/253)).

## What a sensor can do, and what it cannot

**A sensor installed by a citizen does not trigger alerts and never lowers
a score.** Measurements enter at trust levels, and a sensor moves up a level
by proving it measures well, not by claiming it.

| Level | Who | What it can do |
|---|---|---|
| 0 · observer | anyone, after registration | appears on the station map, feeds the verifications and the radar comparison; does not enter the forecast |
| 1 · verified | promoted automatically after weeks of agreement with the Civil Protection radar | can only raise the rainfall estimate, together with sensors of other people, up to a cap |
| 2 · institutional | public bodies, Civil Protection, universities | the only level that can force an alert |

The reason is simple: a clogged rain gauge reading zero must not be able to
say a slope is quiet, and a bumped sensor must not be able to send an alert
to a municipality. It is the same rule that holds across Limen: **a missing
or untrusted datum is not a reassuring one**.

## Safety: where not to install

**No measurement is worth a risk for whoever installs it.**

- Do not install on moving slopes, embankments, riverbeds or below rock
faces.
- Do not install on bridges, embankments or public works without the
authorisation of the body that manages them.
- Do not go to install, check or repair a sensor during an alert.
- On private land you need the owner's permission.
- Limen **is not a personal warning system**: for the safety of people and
property, the bulletins and alerts of the Civil Protection are what count.

A sensor's public position is rounded and the email of whoever registers it
is never published.

## Status

| Step | Status |
|---|---|
| Sensor broker with mTLS, private CA and automatic check ([#260](https://github.com/agent-engineering-studio/limen/issues/260)) | done |
| Trust levels in the engine ([#251](https://github.com/agent-engineering-studio/limen/issues/251)) | done |
| v2 protocol and measurement intake ([#252](https://github.com/agent-engineering-studio/limen/issues/252)) | to do |
| Registration without an account ([#253](https://github.com/agent-engineering-studio/limen/issues/253)) | to do |
| Kit projects with example firmware ([#256](https://github.com/agent-engineering-studio/limen/issues/256)) | to do |
| Measuring the value of non-official rain gauges against the radar ([#250](https://github.com/agent-engineering-studio/limen/issues/250)) | to do |
