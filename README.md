# GameDroid builds

Public build pipeline and downloads for GameDroid, a GameNative fork tuned for the Xiaomi 17 (Adreno 840).
The source is private; this repo only builds it and publishes APKs.

## Install
1. Download `gamedroid-installer.apk` (about 2.4 MB) from the [latest release](../../releases/latest) and install it.
2. Open it. It downloads the newest `gamedroid.apk` and installs it. Open it again any time to update.
   The app also checks for updates by itself once a day.

## How builds happen
`.github/workflows/build.yml` runs every 30 minutes. When GameDroid's `main` has a commit that hasn't been built,
it checks out the private code with the `GAMEDROID_TOKEN` secret, builds the app and installer, runs the unit tests,
and publishes release `build-<commit>`. Only the 5 newest builds are kept.

Secrets: `GAMEDROID_TOKEN` (read-only token for the private repo) and `GAMEDROID_KEYSTORE` (base64 signing key, so
each build installs over the last). Scheduled builds are paused until the key secret exists; a manual run works without it.
