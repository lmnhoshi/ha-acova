# Changelog

## 0.1.1 (2026-11-02)

- Fix links in the README, which were broken when viewed in HACS or Marketplace

## 0.1.0 (2026-11-02)

First version.

- Discovery and pairing through the config flow
- Mode select, temperature number and climate entities
- Open-window detection switch
- Weekly schedule sync from a Schedule helper, with the `acova.sync_schedule` action
- Refresh button and last read sensor, with no polling
- Read-only `probe.py` hardware check

### Known issues

- Home Assistant 2026.11 logs that `_attr_temperature_unit` and `target_temperature` are deprecated. They stop working in 2027.11, so the climate entity must move to `_attr_native_temperature_unit` and `native_target_temperature` before then, which raises the minimum Home Assistant version.
