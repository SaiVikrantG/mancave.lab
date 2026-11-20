# mancave.lab — current state

Homelab on an old HP laptop (8 GB, 2 TB HDD, i7-8565U) running Proxmox VE 9.2, paired with a VPS, connected over Tailscale. Goal: hands-on infra practice (virtualization, IaC, monitoring, networking). Last reviewed 2026-11-19.

## Topology

```
Phone, MacBook, VPS ── Tailnet ──┬─ HP host (pve.mancave.lab, 192.168.50.10)
                                 └─ via ts → 192.168.50.0/24 (lab subnet, behind TP-Link, behind AirFiber/CGNAT)
```

## What's up

| vmid | LXC      | IP       | Role                                               |
| ---- | -------- | -------- | -------------------------------------------------- |
| 101  | ts       | .102     | Tailnet peer; advertises 192.168.50.0/24 subnet route |
| 102  | wizmood  | .104     | Spotify-reactive Philips WiZ bulb driver           |
| 103  | pihole   | .5       | DNS + blocklist for the lab (`*.mancave.lab`)       |

**VPS:** Prometheus + Grafana + Alertmanager (compose), scraping node_exporter on HP + 3 LXCs + VPS. Also hosts my own service (`chckpoint`). HP host and `ts` LXC are independent tailnet peers.

## What's next (in order)

1. Alerting wired up (AM → ntfy) + community Grafana dashboards + blackbox_exporter probing VPS from lab
2. **IaC loop** — Terraform/OpenTofu + Ansible + cloud-init, full destroy-and-rebuild
3. HA DNS (secondary resolver on VPS) — Prom scrapes use `*.mancave.lab`, so Pi-hole is currently a SPOF
4. Tier-2 service discovery: move DHCP from TP-Link to Pi-hole/dnsmasq (auto DNS from leases)
5. Parallel WireGuard mesh VPS↔HP as tailnet-outage fallback

## Known constraints / risks

- 8 GB RAM, 5400 RPM HDD, CGNAT upstream (no inbound) → Tailscale is the only remote access
- Dead CMOS cell (BIOS + clock reset on power loss), dead laptop battery, inverter stands in as UPS
- Single disk, no redundancy — backups to VPS planned, not done
- One Pi-hole, no DNS replica
