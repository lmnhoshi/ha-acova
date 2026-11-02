# Publishing checklist

For the maintainer. Delete this file if you'd rather not publish it.

## Before the first release

1. Replace the placeholders, then check that none remain:
   ```sh
   grep -rn -E 'YOUR_GITHUB_USERNAME|YOUR_NAME' . --exclude=PUBLISHING.md --exclude-dir=.git
   ```
   They are in `manifest.json`, `README.md` and `LICENSE`. If you choose another repository name than `ha-acova`, change that too.
2. Update `docs/HARDWARE_NOTES.md` with the schedule, window switch and phone app results.

## Create the repository

This folder currently sits inside the homelab repository. Publish it as its own repository:

```sh
cd homeassistant/acova
git init -b main
git add .
git commit -m "First version"
gh repo create ha-acova --private --source=. --push   # make it public once checks pass
gh repo edit --description "Local Bluetooth control of Acova radiators in Home Assistant" --add-topic home-assistant --add-topic hacs --add-topic bluetooth
```

## Check it

- Both GitHub Actions workflows must pass. The HACS check only works on a public repository.
- Install it in Home Assistant as a HACS custom repository. In Home Assistant 2026.11, HACS is built in as **Marketplace**.

Done for 0.1.0: hassfest, HACS and tests passed, and it installed through Marketplace.

## Release

Raise `version` in `manifest.json`, add a `CHANGELOG.md` entry, commit and push, then tag the same version:

```sh
gh release create v0.1.0 --title "0.1.0" --notes-file CHANGELOG.md
```

## HACS default list

Custom repository installs work straight away. To appear in HACS search, follow the current [HACS publishing guide](https://www.hacs.xyz/docs/publish/). Real-world reports from a few more users first would be sensible.
