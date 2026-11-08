# Apex Engine — Garmin & Premium UI update

## Included in this revision

- Expanded Garmin daily and historical retrieval for HRV, resting heart rate, sleep, sleep stages, sleep target, Garmin Training Readiness, Body Battery, stress, respiration, SpO2, steps, distance, floors, calories, intensity minutes, hydration, training status/load focus, VO2max, FTP, lactate threshold, running economy and endurance score where the account exposes them.
- Added 7-night and 28-night sleep averages from stored daily records.
- Added Garmin multi-factor authentication handling without a server-side console prompt.
- Added scalar RHR parsing, weekly resting-HR retrieval and more tolerant response parsing.
- Kept Garmin Training Readiness separate from Apex Readiness.
- Expanded Supabase schema migration and the dashboard metric catalogue.
- Changed the UI to a restrained graphite, sage and warm-stone theme with calmer typography and primary buttons.
- Added regression tests for scalar RHR, hydration and running-economy parsing.

## Important limitations

- Garmin Connect access uses an unofficial community wrapper. A successful sync can only retrieve metrics returned for the connected account, device, sensors, activities, region and current endpoint behaviour. There is no guarantee that every Garmin metric exists for every user.
- Advanced activity dynamics, power curves, detailed zone time and other telemetry may require additional per-activity detail calls or FIT-file processing.
- Live Garmin, Supabase and Gemini calls were not run in the build environment. Those require the user's own credentials, database and installed dependencies.
- This is not a production-ready commercial Garmin integration. Review Garmin's Developer Program terms before offering this to multiple users commercially.
