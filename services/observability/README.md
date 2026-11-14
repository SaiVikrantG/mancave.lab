# observability

Docker-compose stack that runs the VPS's Prometheus + Grafana + Alertmanager
trio. Configs live in sibling dirs:

- `../prometheus/` — scrape config + alert rules
- `../grafana/` — datasource + dashboard provisioning and dashboard JSONs
- `../alertmanager/` — routing + receivers

Joins the chckpoint `deploy_default` network as `external` so Prom can scrape
chckpoint by container name once chckpoint exposes `/metrics`.

## Deploy

On the VPS, from inside `services/observability/`:

```
docker compose up -d
docker compose ps
```

## UIs (tailnet-only)

Bound to the VPS tailnet IP `100.113.225.49` — not public.

- Prometheus: http://100.113.225.49:9090
- Grafana:    http://100.113.225.49:3000 (admin/admin; forced change on first login)
- Alertmanager: http://100.113.225.49:9093

Confirm nothing leaked to public:

```
nmap -Pn -p 9090,3000,9093 <vps-public-ip>  # all three should be filtered/closed
```

## Reloads

Config edits (prometheus.yml, alertmanager.yml, provisioning) don't need a
container restart — SIGHUP the running process:

```
docker exec prometheus kill -HUP 1
docker exec alertmanager kill -HUP 1
```

Grafana picks up provisioning changes on container restart; dashboards drop in
live from `../grafana/dashboards/`.

## Retention

Prometheus retention is set via flags (not config file):

- `--storage.tsdb.retention.time=120d` — primary cap
- `--storage.tsdb.retention.size=25GB` — secondary cap (defense)

Changing these requires a container restart (`docker compose up -d` after edit).
