# grafana

Provisioning + dashboards for the VPS Grafana. Deployed by the compose stack
in `../observability/`.

- `provisioning/datasources/` — datasource configs loaded at boot
- `provisioning/dashboards/` — dashboard *providers* (points at the dashboards folder)
- `dashboards/` — dashboard JSON files; drop in community exports (1860, etc.)

Default credentials on first boot: `admin` / `admin`. Grafana forces a password
change on first UI login. If you miss that and lock yourself out, reset via:

```
docker exec grafana grafana-cli admin reset-admin-password <newpass>
```

UI edits are allowed and persist in the SQLite DB, but dashboards under
`dashboards/` are the source of truth and will be re-applied on provider reload.
