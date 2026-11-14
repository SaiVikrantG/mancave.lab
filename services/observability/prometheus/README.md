# prometheus

Scrape config and alert rules for the VPS Prometheus. Deployed by the compose
stack in `../observability/`.

- `prometheus.yml` — scrape config; add new `scrape_configs` entries here
- `alerts/*.yml` — alert rule files; loaded via `rule_files` glob

After editing either, reload Prom in place (no restart):

```
docker exec prometheus kill -HUP 1
```

Full restart only needed for flag changes (retention, listen address, etc.).
