# Personal data

**Limen has no accounts, uses no cookies and does not track who looks at the
map.** Reading the map, the regions, the municipalities, the verifications and
the guides requires nothing from you. Personal data enters in three cases
only, each one by choice of whoever writes: an expert contribution, a sensor
registration, receiving alerts. This page says which data, why, for how long
and how to delete it.

> **Whoever installs Limen** becomes the controller of their installation's
> data, in particular of the alert recipients they configure. This page
> describes the project's public installation: whoever runs another one must
> adapt controller, contact and retention times, and publish their own
> version.

## Who the controller is

For the public installation of Limen the data controller is the maintainer of
the Limen project. For any request about personal data:
**gzileni@agentengineering.it**.

## What enters, why, for how long

| When | Which data | Why | Legal basis | For how long |
|---|---|---|---|---|
| You visit the site | the IP address, in the web server log | security and fault diagnosis | legitimate interest (Art. 6.1.f GDPR) | 14 days, then the log is deleted |
| You send an expert contribution | name or profile, email, organisation (optional), text | to get back to you about that contribution | consent, given with the form's checkbox (Art. 6.1.a) | not stored by Limen: it stays only in the email received by the maintainer, deleted after 12 months |
| You send an expert contribution | the IP address | to limit submissions, against spam | legitimate interest (Art. 6.1.f) | in memory only, one hour; never written to disk |
| You register a sensor | email, exact position of the sensor, photos and notes | to answer the request, tie the sensor to a cell, delete everything when you ask | performance of your request (Art. 6.1.b) | email and position while the sensor is registered; photos and notes only in the email to the maintainer, deleted after 12 months |
| You receive alerts | email address or Telegram chat | to send you the alerts | decided by the organisation running the installation | until the organisation removes you from the list |

**What never enters.** No personal data goes to the artificial intelligence
models: the regions' explanatory texts are written from numbers and place
names. No personal data is published on the map, in the APIs or in the agent
tools. Sensor measurements are published under CC BY 4.0 and contain no
personal data: on the map a sensor's position is rounded to about one
kilometre.

## Who else sees the data

- **The email provider** of the installation, which delivers the emails of
  contributions, registrations and alerts.
- **Telegram**, for those who receive alerts in a chat.
- **While you look at the map**, your browser downloads directly from other
  servers the base map (OpenStreetMap,
  [privacy policy](https://osmfoundation.org/wiki/Privacy_Policy)) and the
  text fonts (Google Fonts,
  [privacy policy](https://policies.google.com/privacy)). Those servers see
  your IP address as for any site that uses them; Limen receives nothing from
  them.

No data is sold or handed to others, nor transferred outside the European
Union by Limen.

## Your rights

At any time you can ask to see, correct or delete your data, to restrict its
use or to object, and you can withdraw the consent given for a contribution.
Write to **gzileni@agentengineering.it**: we answer within one month. For a
sensor, just reply to Limen's email: the email is deleted, the devices are
revoked and the position goes back to the centre of the one-kilometre cell;
the measurements already collected remain, with nothing left that links them
to you.

If you believe your data is being handled improperly, you can contact the
Italian [data protection authority (Garante per la protezione dei dati
personali)](https://www.garanteprivacy.it).

## For developers and installers

- **Contributions**: `src/limen/core/contributi.py`. The per-IP limit lives in
  an in-memory dictionary with a 3600 s window (`Limitatore`); the
  `contributi.*` logs contain neither email nor IP.
- **Sensors**: tables `sensori_registranti` (email) and `sensori_richieste`
  (position, migration 077); the `sensori.registrazione.*` logs carry only
  identifiers. Deletion: `limen sensore cancella-registrante <email>`.
- **Logs**: with the compose's Caddy proxy there is no access log; with nginx
  on the host (`infra/nginx/limen.conf.template`) the `limen.access.log` log
  rotates with the package's logrotate (14 days on Debian and Ubuntu).
  Container logs are capped at 3 files of 10 MB per service.
- **Alert recipients**: `NOTIFICATIONS__EMAIL__RECIPIENTS` and
  `NOTIFICATIONS__TELEGRAM__CHAT_ID` in the installer's `.env`; they do not
  leave the server.
