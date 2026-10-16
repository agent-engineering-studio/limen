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

## Why one more sensor

**On 10 October 2026, in the Reggio Calabria area, the weather model saw a
third of the rain that was falling.** At Melito, San Lorenzo and Bagaladi the
forecasts gave about 50 mm for the day; the Civil Protection radar, corrected
with rain gauges, measured between 110 and 176. On the landslide cells
Limen's weather component never went above 0.29, when reaching "High"
needed 0.65. The ground was right: the real rain was missing.

An autumn thunderstorm over Southern Italy unloads on a few square
kilometres, and official rain gauges are often ten or fifteen kilometres
apart. One more gauge does not decide anything alone, but it tells the radar
where it is wrong, and together with others owned by different people it
raises the rainfall estimate exactly where the official networks do not
reach.

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

**Few fields, fixed units, identity in the certificate.** Limen already
reads messages in this format ([#252](https://github.com/agent-engineering-studio/limen/issues/252)),
but only from registered devices, and registration is not open yet.

Two topics per device:

```
limen/v2/<id>/obs       the measurements
limen/v2/<id>/status    online at connect, offline as last will
```

The device **does not declare where it is**: Limen records its position,
region and grid cell when it approves the device. One less datum to verify,
and a sensor that has been moved gets noticed.

The message follows SenML (RFC 8428), the standard format for sensor
measurements, in JSON. CBOR, where every byte counts, will come with LoRaWAN
([#266](https://github.com/agent-engineering-studio/limen/issues/266)).

```json
[
  {"bn": "pluvio-matera-01/", "bt": 1792065600, "n": "rainfall", "u": "mm", "v": 0.4},
  {"n": "seq", "v": 18342}
]
```

The quantities and their units:

| Quantity | `u` field | For which hazard |
|---|---|---|
| `rainfall` | `mm` | landslide, flood |
| `soil_moisture` | `m3/m3` | landslide |
| `water_level` | `m` | flood (coming) |
| `air_temperature`, `relative_humidity`, `wind_speed` | °C, %, km/h | wildfire (coming) |

The unit is written exactly like this: Limen does not convert, and a
message with a different unit is discarded. A quantity Limen does not know
yet is ignored without discarding the others.

Three rules apply to every message. Time is always UTC, taken from NTP: a
message from the future is discarded. At most about a dozen messages a
minute, counting `status`, the last will and retransmissions too: beyond that they are discarded, and a device that insists goes into
quarantine until someone checks it. The sequence number always grows, even
after a reboot, so it must be kept in the device's memory: a number already
seen is a repeated message and is discarded. A device that loses its network keeps its
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

## Three sensors to build

**An ESP32, the sensor, a weatherproof box and a power supply: between 35
and 60 euros.** Prices are indicative, for single parts bought in Italy.
Inclinometers are left out: they measure a moving slope, and that kind of
data is only trusted from an institution (level 2).

### Tipping-bucket rain gauge

A bucket fills with a fixed amount of rain, empties by tipping over and
briefly closes a reed switch: the ESP32 counts the tips and every five
minutes sends the millimetres that fell.

| Part | Cost |
|---|---|
| ESP32 DevKit (ESP32-WROOM-32) | €8 |
| Spare tipping-bucket gauge for weather stations, reed output | €20 |
| 5 V USB supply, or a 6 W panel with an 18650 battery and charger | €8-20 |
| IP65 box with cable glands | €6 |
| Pole or bracket, cable, terminals | €8 |
| **Total** | **about €50-60** |

| Rain gauge | ESP32 |
|---|---|
| reed wire | GPIO 27 |
| other reed wire | GND |

No resistor is needed: the firmware enables the internal one and ignores the
contact bounce. Every bucket has its own volume: measure it by slowly pouring
a known amount of water and counting the tips, then write `mm_scatto=` on
the serial console. The starting value, 0.2794 mm, is the one of the most
common models.

**Where to put it**, following the World Meteorological Organization rules:
horizontal orifice 1-1.5 m above the ground; away from any obstacle (walls,
trees, fences) at least twice its height above the orifice, four times is
better; not on a roof or next to a building, where the wind swirls and
carries the rain away. Clean the filter once a month: leaves and insects
clog it, and a clogged gauge reads zero.

### Soil moisture

A capacitive probe measures how much water the ground holds, which matters
for a landslide as much as the rain: the same storm brings down an already
saturated slope and not a dry one.

| Part | Cost |
|---|---|
| ESP32 DevKit | €8 |
| Capacitive probe v2.0 with TLC555 (not the NE555 ones, which do not work at 3.3 V) | €3 |
| Three-core shielded cable, 3 m | €3 |
| Power and IP65 box, as above | €15-25 |
| **Total** | **about €35-40** |

| Probe | ESP32 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| AOUT | GPIO 34 |

Push the probe in vertically up to the line, 5-10 cm deep, away from roots
and stones, with the electronics above ground sealed with resin or
heat-shrink. Calibrate it before burying it: `grezza` in air gives
`secco=`, `grezza` with the probe in a glass of water up to the line gives
`bagnato=`. A three-euro probe is off by a few percentage points even when
well calibrated, which is one of the reasons it starts as an observer.

### Water-level gauge

A waterproof ultrasonic sensor mounted above a watercourse measures the
distance to the surface: the level is its height minus that distance.
**Only with the authorisation of the body that manages the watercourse or
the bridge**, and Limen does not read water levels yet: the registration
form will offer it when the flood engine can use it.

| Part | Cost |
|---|---|
| ESP32 DevKit | €8 |
| Waterproof JSN-SR04T (25 cm to 4.5 m) | €10 |
| Two resistors, 1 kΩ and 2 kΩ | €0.5 |
| Bracket, power and IP65 box | €25-35 |
| **Total** | **about €45-55** |

| JSN-SR04T | ESP32 |
|---|---|
| 5V | VIN (5 V) |
| GND | GND |
| TRIG | GPIO 26 |
| ECHO | GPIO 25, through the divider: 1 kΩ to ECHO, 2 kΩ to GND |

The divider is needed because ECHO outputs 5 V and the ESP32 takes 3.3. The
height of the transducer above the gauge zero, in metres, goes in
`quota=`. A millimetre-wave radar (€40-70) measures better in rain and foam,
but the example firmware does not support it.

## The example firmware

**One program for the three sensors, in the Limen repository under
[`firmware/limen-sensore`](https://github.com/agent-engineering-studio/limen/tree/main/firmware/limen-sensore),
compiled on every change.** Flash it with
[PlatformIO](https://platformio.org):

```sh
cd firmware/limen-sensore
pio run -e pluviometro -t upload     # or umidita_suolo, idrometro
pio device monitor                   # the serial console, at 115200
```

There is no secret in the program: network, id and certificates are given
on the serial console and stay in the device memory. The commands are in
Italian, like the rest of Limen:

```
ssid=MyNetwork
password=…
id=pluvio-matera-01
riavvia
csr
```

`csr` creates the device key the first time and prints the request to paste
into the registration form. When the email with the two certificates
arrives, type `cert` and paste the device one, then `ca` and paste the CA
one, then `riavvia` (restart). The firmware refuses a certificate that does
not match its key or that is for another id. Every setting, calibrations
included, takes effect at the next restart. `stato` tells what is missing.

What it does on its own:

- takes UTC time from NTP and does not measure until it has it;
- measures every five minutes, aligned to the clock (`intervallo=` to
change it);
- publishes in SenML with acknowledgement (QoS 1), and announces
`online`/`offline`;
- without network it keeps a day of measurements and sends them back in
groups when it returns, without exceeding the per-minute message limit.
The queue lives in volatile memory: a power drop loses it;
- keeps the sequence number across restarts, and a group sent again keeps
its own: if the first attempt had arrived, Limen discards the second instead
of counting the same rain twice. The acknowledgement comes from the broker,
not from Limen: a message Limen discards is lost, which is why the firmware
sends at most six a minute.

**The key in memory is in clear.** For a device left outdoors, where anyone
can take it, enable the ESP32's flash encryption and secure boot, or keep the
key in an ATECC608.

## How to connect it

| Link | When | Status |
|---|---|---|
| Wi-Fi with an ESP32 | there is a network in range, at home, at school | the example firmware |
| Raspberry Pi Pico W | like the ESP32; TLS with mbedTLS or MicroPython | no example |
| Raspberry Pi | already runs Linux: `mosquitto_pub` or Paho are enough | see below |
| LoRaWAN with The Things Network | in the countryside, no Wi-Fi, kilometres of range | coming ([#266](https://github.com/agent-engineering-studio/limen/issues/266)) |
| Arduino Uno | — | **no**: it cannot do TLS |

From a Raspberry Pi, or from a computer for a test, a message is sent like
this (the sequence must grow at every send):

```sh
mosquitto_pub -h limen.agentengineering.it -p 8883 -q 1 \
  --cafile ca.crt --cert dispositivo.crt --key dispositivo.key \
  -t limen/v2/pluvio-matera-01/obs \
  -m "[{\"bn\":\"pluvio-matera-01/\",\"bt\":$(date +%s),\"n\":\"rainfall\",\"u\":\"mm\",\"v\":0.0},{\"n\":\"seq\",\"v\":1}]"
```

## How to register a sensor

**No account: a form, an email, a person who approves.** The form is at the
bottom of this page and opens when the network accepts new devices
([#253](https://github.com/agent-engineering-studio/limen/issues/253)). It
asks for the sensor type, the position, the device CSR, an email address and
three confirmations: the data licence, the safety rules and the notice
below. The installation photo is optional.

The CSR is generated on the device or, for a test, on a computer:

```sh
openssl ecparam -name prime256v1 -genkey -noout -out dispositivo.key
openssl req -new -key dispositivo.key -subj "/CN=pluvio-matera-01" -out dispositivo.csr
```

The CN is the device id: lowercase letters, digits and hyphens, 3 to 63
characters. The form takes the content of `dispositivo.csr`. **The `.key`
file is never sent**, not even to Limen: if you paste it, the form stops.

The request creates nothing by itself: it is emailed to the Limen
maintainers, who read it and approve or reject it. If they approve it, you
receive the device certificate and the CA certificate by email, and the
sensor enters the registry as an observer. Each person can register at most
three devices; a revoked device still counts.

## Personal data

Limen keeps two pieces of personal data about whoever registers a sensor:
**the email address and the exact position of the sensor**. The address is
used to reply to the request, to count how many devices the same person has
registered and to delete everything on request. It is never published and
no Limen interface exposes it: not the map, not the APIs, not the agent
tools.

- **Position.** The exact one is needed to bind the sensor to a grid cell,
and it is not published. When stations appear on the map, the public
position will be rounded to 0.01° (about one kilometre).
- **Photo and notes.** They travel only in the email to the Limen
maintainers and are not stored in the database.
- **Measurements.** They are published under the CC BY 4.0 licence and
contain no personal data.
- **Deletion.** Just reply to Limen's email. The address is deleted, the
devices are revoked and their position goes back to the centre of their
one-kilometre cell: the measurements already collected stay, with nothing
left linking them to you.

## Data licence

**The measurements of a registered sensor are published under the
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) licence.** Anyone
can reuse them, commercial uses included, crediting Limen and the station.
The registration form asks for it explicitly: it is what lets a
municipality, a university or another network use them. The measurements
contain no personal data; the public position of the station is rounded
(see above).

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
| v2 protocol and measurement intake over MQTT ([#252](https://github.com/agent-engineering-studio/limen/issues/252)) | done |
| Signed HTTP intake ([#265](https://github.com/agent-engineering-studio/limen/issues/265)) and LoRaWAN from The Things Network ([#266](https://github.com/agent-engineering-studio/limen/issues/266)) | to do |
| Registration without an account ([#253](https://github.com/agent-engineering-studio/limen/issues/253)) | done, the form opens with the network |
| Kit projects with example firmware ([#256](https://github.com/agent-engineering-studio/limen/issues/256)) | done |
| Measuring the value of non-official rain gauges against the radar ([#250](https://github.com/agent-engineering-studio/limen/issues/250)) | to do |
