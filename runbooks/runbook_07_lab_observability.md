# Runbook 07: Lab observability — Prom + Grafana + Alertmanager on the VPS

**When to use this:** standing up end-to-end monitoring that covers the lab (HP + LXCs, over the tailnet) and the VPS itself (host + chckpoint stack), with alerts routed to ntfy. Also the first "lab watches VPS" link via blackbox_exporter on an LXC probing chckpoint's public URL.

**Prereqs:**
- Pi-hole LXC live (runbook 06), HP + `ts` LXC + VPS all on the tailnet
- chckpoint already deployed on the VPS via docker-compose (same pattern we're matching)
- Admin access to the Tailscale admin console (to approve advertised routes)
- Repo clean on `main`

**Not covered (deliberately):** cAdvisor, Loki, VPS Pi-hole replica, a second Prometheus on the lab, Pushgateway (slot reserved, uncomment when a benchmark run is actually imminent), chckpoint repo edits (`/metrics` exposure + Caddy admin — pattern documented at the end of this runbook, wiring is done in the chckpoint repo).

**Expected time:** 3–4 hrs if you don't get stuck; more if the Tailscale route approval or ntfy webhook misbehave.

# Operation: Eyes Everywhere

A monitoring adventure in 3 acts, 9 quests, and 1 real boss fight (a self-induced alert).
**Class:** Homelab Journeyman (Lv. 6 — just dinged after Pi-hole)
**Party:** you, the HP, the `ts` LXC, the VPS, and chckpoint standing in the back pretending it exposes `/metrics` already
**Final boss:** The Silent Oracle, who stores every truth but refuses to tell you when it changes
**Reward:** a Grafana you can open from your phone showing graphs of everything, and a phone that buzzes when something's on fire.

## 🎒 Loadout check

- [ ] Pi-hole LXC live (runbook 06), HP + `ts` LXC + VPS all on the tailnet (+10 XP for being here)
- [ ] chckpoint already deployed on the VPS via docker-compose (same pattern we're matching)
- [ ] Admin access to the Tailscale admin console
- [ ] Repo clean on `main`
- [ ] A drink. Still non-negotiable.

**Not covered (deliberately):** cAdvisor, Loki, VPS Pi-hole replica, a second Prometheus on the lab, Pushgateway (slot reserved, uncomment when a benchmark run is actually imminent), chckpoint repo edits — `/metrics` exposure + Caddy admin pattern is documented at the end of this runbook, wiring is done in the chckpoint repo.

## 🗺️ Quest map

| Act | # | Quest | Done |
|---|---|---|---|
| I | 1 | Open the Gate (subnet router on `ts`) | [x] |
| I | 2 | Raise the Watchtower (Prom + Graf + AM compose stack on VPS) | [x] |
| I | 3 | Plant the Sensors (node_exporter × 4; wizmood skipped) | [x] |
| I | 4 | Wire the Nerves (scrape config + placeholder jobs) | [x] |
| I | ⚔️ | **Mini-boss:** every target green on Prom's `/targets` page | [x] |
| II | 5 | Paint the Walls (community dashboards 1860, Caddy, Go) | [x] |
| II | 6 | Watch Outward (blackbox_exporter — first lab-watches-VPS link) | [ ] |
| II | 7 | Count the Queries (`eko/pihole-exporter`) | [ ] |
| III | 8 | Teach the Oracle to Speak (Alertmanager rules + ntfy) | [ ] |
| III | ⚔️ | **Boss:** induce a real alert, phone buzzes, oracle wakes you | [ ] |
| III | 9 | Mark the Timeline (Grafana annotations from CLI) | [ ] |
| III | 🎁 | Loot collection (topology + context + commit) | [ ] |

---

## 🗺️ ACT I — "Lay the Pipes"

*Everything in this act is reversible. The stack exists but nothing on your phone depends on it yet. You can rage-quit any time.*

### 🎯 Quest 1 — Open the Gate (+100 XP)

**Objective:** teach `ts` to carry traffic for `192.168.50.0/24`, so the VPS (and the rest of the tailnet) reaches lab IPs directly over the overlay.

**Why `ts` and not the HP host:** the LXC is already the designated "network stuff" node — its whole reason for existing is Tailscale. Blast radius of a routing bug or a reauth stays inside vmid 101; the host stays "just the hypervisor." Downside: `ts` becomes load-bearing for VPS→lab scraping. Mitigated by the fact that if `ts` dies, HP probably died with it. Re-evaluate this choice if you later add bulk tailnet transfer (restic, Jellyfin, Loki).

**Three moves:**

1. Flip the kernel's forwarding switch for v4 and v6, in a drop-in under `/etc/sysctl.d/` so it survives reboots. Apply without a reboot.
2. On `ts`, tell `tailscaled` to advertise `192.168.50.0/24`. Keep MagicDNS off (`--accept-dns=false`) — Pi-hole owns resolv.conf on this LXC, don't let Tailscale touch it.
3. Approve the route in the Tailscale admin console (routes advertised ≠ routes approved — a human has to tick the box). Then on the VPS, consume routes with `--accept-routes`.

**Boss mechanic 1 — the silent dropper.** `tailscale up --advertise-routes` does **not** flip the `ip_forward` sysctl. Advertise without forwarding = Tailscale happily tells the tailnet "I'm your gateway," then the kernel drops every packet. No error, no log line screaming. First symptom is `tailscale ping` from VPS timing out. Set the sysctl *first*, verify with `sysctl` *before* running `tailscale up`.

**Boss mechanic 2 — the flag-eater.** `tailscale up` **replaces** the flag set, it doesn't merge. If `ts` already runs with any flags (SSH, exit-node, tags, hostname override), re-pass them in the advertise-routes command or they vanish. Check the current flags first — `tailscale status --json | jq '.Self'` is one way to find them, or `grep ExecStart /etc/systemd/system/tailscaled*` for a historical hint.

**Boss mechanic 3 — the admin console tick.** Advertising only *offers* the route. Until a human approves it in the admin console (Machines → `ts` → Edit route settings), no other tailnet peer sees it. If `tailscale status` on the VPS shows the route listed but packets don't flow, the tick is the thing to check.

**Achievement 🏆 "Route Approved"** — the admin console shows `192.168.50.0/24` ticked on `ts`, and `tailscale status` on the VPS lists `ts` as a subnet router.

**⚔️ Verification (the actual test, not just the UI):**

From the VPS:
- `tailscale ping 192.168.50.10` succeeds, output should name `via 192.168.50.0/24 subnet route from ts`. If it says `via DERP` or routes to a `100.x.x.x` address, the subnet route isn't the path being used — recheck console tick and `--accept-routes`.
- `curl -s http://192.168.50.5/admin/` returns Pi-hole admin HTML. ICMP working but TCP not = Tailscale ACL or Proxmox firewall issue, not routing.

From the HP host (sanity — advertising shouldn't touch local routing):
- `ping -c 2 192.168.50.5` still works. If this broke, something went very wrong — rollback.

**Rollback:** untick route in admin console (instant — all peers stop using it). `tailscale down && tailscale up` on `ts` without `--advertise-routes` to clear the offer side. `tailscale up` on VPS without `--accept-routes`. Leave the sysctl file alone, forwarding on an idle LXC is harmless.

**Gotchas vault:**
- `ip_forward` is not auto-set by `--advertise-routes`.
- `tailscale up` replaces flags, doesn't merge. Modern Tailscale (~1.60+) catches this and refuses to proceed unless you either pass `--reset` or re-pass every non-default flag it suggests. Don't rely on this safety net — check `tailscale debug prefs` beforehand anyway.
- Route needs admin console approval before anything flows. `tailscale debug prefs` shows `AdvertiseRoutes`; `PrimaryRoutes` only populates after approval.
- Subnet routes live in a **separate kernel routing table** (table 52 by default) via `ip rule`, not the main table. `ip route` on the accepting peer won't show them — use `ip route show table all | grep tailscale` or just `tailscale ping`.
- Lab-name resolution over the tailnet is a separate problem (Pi-hole isn't on the tailnet). This quest gives IP-level reach only, which is enough — Prom's scrape config will use IPs.
- **UDP GRO warning on subnet routers.** `tailscale up` prints a warning about `rx-udp-gro-forwarding` on the inbound interface. Cosmetic for low-bandwidth lab traffic (~KB/s metrics scrapes). Fix if/when `ts` routes bulk traffic (restic, Jellyfin, Loki). See [tailscale.com/s/ethtool-config-udp-gro](https://tailscale.com/s/ethtool-config-udp-gro).

---

### 🎯 Quest 2 — Raise the Watchtower (+120 XP)

**Objective:** three containers (`prometheus`, `grafana`, `alertmanager`) stand up on the VPS as a sibling docker-compose stack to chckpoint. UIs bound to the tailnet IP (not public). Prom retention 120d. Pushgateway slot commented out for later. Shared docker network with chckpoint so future `/metrics` scrapes work by container name.

**VPS baseline (measured 2026-11-11):** 48G disk, 42G free; 3.8G RAM, 3.2G available; 1 CPU core; no swap; `/var/lib/docker` at 634M. Comfortable headroom for 120d retention + stack footprint.

**Five moves:**

1. **Scaffold the repo structure.** Create `services/prometheus/`, `services/grafana/`, `services/alertmanager/`, and `services/observability/` (hosts the unified compose file). Each service dir holds its own configs (scrape, alerts, provisioning, routing); the compose file in `observability/` references them via relative mounts. Commit to repo.
2. **Write the configs** — minimal first-pass:
   - `prometheus/prometheus.yml`: one job scraping Prom itself (self-scrape). Scrape config for node_exporters and placeholder jobs lands in Quest 4.
   - `prometheus/alerts/`: empty directory with a `.gitkeep` — rules land in Quest 8.
   - `grafana/provisioning/datasources/prometheus.yml`: Prom as the default datasource, pointing at `http://prometheus:9090` (docker network name).
   - `grafana/provisioning/dashboards/`: provider config; dashboard JSONs land in Quest 5.
   - `alertmanager/alertmanager.yml`: skeleton with a null receiver (we wire ntfy in Quest 8).
3. **Write the compose file.** All three services, shared docker network (`observability_net`), tailnet-IP port binding (`100.113.225.49:<port>:<port>`), named volumes for persistence (`prom-tsdb`, `grafana-data`, `am-data`). Restart policy `unless-stopped`. Retention flag: `--storage.tsdb.retention.time=120d --storage.tsdb.retention.size=25GB` (size cap as safety net).
4. **Sync to VPS and bring up.** `scp -r services/` or git pull on the VPS; `docker compose -f services/observability/docker-compose.yml up -d`; watch for pull/start errors.
5. **Verify each UI over tailnet.** From the Mac on tailnet (not public!): `curl` and browser-check `http://100.113.225.49:9090` (Prom), `:3000` (Grafana — first-login `admin`/`admin`, forced password change), `:9093` (Alertmanager). Confirm docker network has chckpoint reachable (join the network; verify DNS resolution of chckpoint container name).

**Boss mechanic 1 — port binding.** docker-compose's default `ports: - "9090:9090"` binds to `0.0.0.0` (all interfaces), making Prom reachable publicly on `:9090`. The firewall currently drops public traffic to `9090` (we saw `nmap` only shows 80/443 as open), so it'd "work" — but relying on the firewall as the only barrier is bad defense-in-depth. Explicitly bind to the tailnet IP: `ports: - "100.113.225.49:9090:9090"`. Then even if the firewall is misconfigured later, the port isn't on `eth0` to begin with.

**Boss mechanic 2 — Grafana first-login dance.** Default creds are `admin`/`admin`. Grafana forces a password change on first UI login. If you miss that step and the container restarts mid-way, you may need to reset via `grafana-cli admin reset-admin-password <newpass>` inside the container. Set the password immediately after first login.

**Boss mechanic 3 — Prom config reload (updated 2026-11-17).** **DO NOT rely on `docker exec prometheus kill -HUP 1` after a `git pull`.** Reason: bind-mounted single files use inode-level binding. When `git pull` (or any editor's atomic-replace save) rewrites `prometheus.yml`, the file's **inode changes** — the host path points at a new inode while the container's bind mount still points at the orphaned old one. SIGHUP then reloads the old content silently. Hashes between host and container diverge and `/targets` shows stale config. **Fix:** `cd services/observability && docker compose restart prometheus` after `git pull`. Same recipe for Alertmanager after AM config changes. Grafana already requires a restart for provisioning changes. One uniform "restart after pull" rule for all three. SIGHUP still works if you edit the file *in place* preserving the inode (e.g. `cat new > existing` or `vim` with `:set backupcopy=yes`), but git pull doesn't, so assume restart.

**Boss mechanic 4 — shared docker network with chckpoint.** For Prom to scrape chckpoint by container name later (`checkpoint:8080/metrics`), both stacks must be on the same docker network. Either declare the network as `external: true` in the observability compose file (if chckpoint created it) or add chckpoint to a network created by observability. Pick one; document which.

**Achievement 🏆 "Three Towers Up"** — all three UIs load over tailnet, Prom's `/targets` shows its self-scrape as UP, Grafana has Prom as a provisioned datasource, Alertmanager status page loads.

**⚔️ Verification:**

- [ ] `docker compose ps` on VPS shows all three services `Up` and healthy
- [ ] `curl -sf http://100.113.225.49:9090/-/healthy` returns 200 (Prom healthy)
- [ ] `curl -sf http://100.113.225.49:3000/api/health | jq .database` returns `"ok"` (Grafana healthy)
- [ ] `curl -sf http://100.113.225.49:9093/-/healthy` returns 200 (AM healthy)
- [ ] `nmap -Pn -p 9090,3000,9093 200.141.5.77` from Mac shows all three as **filtered or closed** (not `open`) — proves nothing leaked to public
- [ ] `docker exec prometheus wget -qO- http://checkpoint:<port>/healthz` reaches chckpoint by container name (network wiring works)
- [ ] Grafana shows Prom as default datasource under Configuration → Data sources, with green "working" check

**Rollback:** `docker compose down -v` in `services/observability/` tears it all down including volumes. No changes to chckpoint's own compose required if we got the network wiring right. Firewall stays unchanged (never opened new public ports).

**Gotchas vault:**
- Binding to a specific IP requires that IP to exist on the host *when the container starts*. If Tailscale isn't up yet at Docker boot time, the container fails to start. Fix: `depends_on` won't help cross-service; instead, make Tailscale a `systemd` dependency of `docker.service`, or use `0.0.0.0` + firewall + explicit nftables rule.
- Grafana + SQLite (default) is fine for a lab; don't switch to Postgres unless you have a reason.
- Alertmanager without a route = silently drops alerts. Our skeleton uses a null receiver, which logs-but-discards — good for Quest 2, replaced in Quest 8.
- Prom's `--storage.tsdb.retention.size=25GB` is a secondary cap; `--retention.time=120d` is the primary. Whichever hits first wins. We set both as defense.
- `docker compose` (v2, no hyphen) vs `docker-compose` (v1, hyphenated) — use v2 on anything modern. Both work if installed; the configs are identical.
- **Don't guess image tags.** Plausible-looking versions (`grafana/grafana-oss:13.3.1` when the real latest is `13.0.2`) will cascade-fail the whole stack when one pull errors. Verify against `https://hub.docker.com/v2/repositories/<repo>/tags/?page_size=100&ordering=last_updated` — three curl calls in a loop with `jq` filtering to semver tags is faster than a browser visit.
- **Bind-mounted single files + `git pull` = inode trap.** When git atomically renames a file into place, bind mounts bound to the old inode don't follow. The container keeps seeing stale content; SIGHUP then "reloads" the old content. Debug: `md5sum` the file on host vs `docker exec <ctr> md5sum <path>` — mismatch is the signature. Fix: `docker compose restart <service>` after every config pull. Only `cat > file` / in-place edits preserve the inode. Alternative: bind-mount the directory (not the file) — but that can shadow image-shipped defaults; audit before switching.
- **`newgrp <group>`** refreshes group credentials in-place after `usermod -aG <group> <user>`, so the current shell sees the new membership without a logout/login. Spawns a subshell with that group as the primary; `exit` returns to the original shell.
- **Docker group = root-equivalent** via `/var/run/docker.sock`. Any member can mount `/` into a container and escape. Running compose as `vikrant` instead of `root` is a hygiene win (cleaner audit trail, SSH deploy keys stay in `/home/vikrant/.ssh`), not a security win.
- **Sparse-checkout in cone mode** is the clean way to put just one service dir on a VPS. `git sparse-checkout init --cone` + `set services/observability` + `checkout main`. `git pull` only touches the checked-out paths afterward.

### 🎯 Quest 3 — Plant the Sensors (+80 XP)

**Objective:** install `node_exporter` on all five hosts so each exposes host-level metrics (CPU, RAM, disk, network, load, filesystem) on `:9100`. VPS gets it as a docker container alongside the observability stack; lab hosts get it as a systemd binary. Verification per host is `curl :9100/metrics` from the VPS or the Mac over the tailnet — scrape config wiring deferred to Quest 4.

**Per-host approach:**

| Host | Deployment | Firewall step |
|---|---|---|
| **VPS** | docker container on `observability_net`, `pid: host` + mounted `/proc`, `/sys`, `/` read-only | none — docker DNS + tailnet-IP bind |
| **HP (`pve`)** | systemd + binary at `/usr/local/bin/node_exporter`, dedicated `node_exporter` system user | skip — Proxmox firewall layer complicates; trust LAN boundary |
| **ts** | systemd + binary, same pattern as HP | skip — bare LXC, no existing firewall |
| **pihole** | systemd + binary | ✅ amend `/etc/nftables.conf`: add `9100` to the existing `dport { 22, 53, 80 }` set, `systemctl restart nftables` |
| **wizmood** | ⛔ **skipped** | Host-level metrics tell you little about a Spotify-reactive bulb service. Covered in Quest 6 by a blackbox probe against `:8080` (the dashboard — proves "service is responding"). Later, instrument wizmood itself for Spotify API cache stats / audio-tap packet rate / etc. — same pattern as chckpoint's deferred `/metrics` exposure. |

**Five moves (one per host), in order of difficulty:**

1. **VPS** — add `node-exporter:v1.12.1` service to `services/observability/docker-compose.yml`, commit, pull on VPS, `docker compose up -d`.
2. **HP + ts** (shared systemd pattern) — download binary, SHA256-verify, install to `/usr/local/bin/`, create unprivileged `node_exporter` user, drop systemd unit, enable.
3. **pihole** — same systemd pattern + amend nftables.
4. **wizmood** — same systemd pattern + amend nftables.
5. **Verify each target** — `curl -sS http://<host-ip>:9100/metrics | head -5` from Mac returns Prom-format output. All five green = Move 5 done.

**Install recipe for systemd hosts (HP, ts, pihole, wizmood):**

```bash
NE_VERSION=1.12.1
cd /tmp

# Download tarball + checksums together
curl -sSL -O "https://github.com/prometheus/node_exporter/releases/download/v${NE_VERSION}/node_exporter-${NE_VERSION}.linux-amd64.tar.gz"
curl -sSL -O "https://github.com/prometheus/node_exporter/releases/download/v${NE_VERSION}/sha256sums.txt"

# Verify BEFORE extracting — do not proceed if this fails
sha256sum -c sha256sums.txt --ignore-missing
# Expected: node_exporter-X.Y.Z.linux-amd64.tar.gz: OK

tar xzf node_exporter-${NE_VERSION}.linux-amd64.tar.gz
sudo install -o root -g root -m 0755 node_exporter-${NE_VERSION}.linux-amd64/node_exporter /usr/local/bin/node_exporter
rm -rf /tmp/node_exporter-${NE_VERSION}.linux-amd64* /tmp/sha256sums.txt

sudo useradd --system --no-create-home --shell /usr/sbin/nologin node_exporter
```

Then the systemd unit at `/etc/systemd/system/node_exporter.service`:

```ini
[Unit]
Description=Prometheus node_exporter
Wants=network-online.target
After=network-online.target

[Service]
Type=exec
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter --web.listen-address=:9100
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
PrivateTmp=yes
PrivateDevices=yes

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter
sudo systemctl status node_exporter --no-pager -l | head -20
```

**Boss mechanic 1 — don't skip the SHA256 check.** `curl` over HTTPS verifies transport, not content. A compromised GitHub release or CDN mirror would still serve a plausible-looking tarball. Download the `sha256sums.txt` from the same release, verify with `sha256sum -c --ignore-missing` **before** extracting or installing. Don't delete the tarball until verification passes. For stricter paranoia levels, use Prometheus's GPG-signed releases — overkill for a homelab but documented in Prometheus's release notes.

**Boss mechanic 2 — the `node_exporter` user has no home and no shell.** `--no-create-home --shell /usr/sbin/nologin` means the service user can never interactively log in, has no writable home dir to persist tooling. Minimal attack surface. If the service is compromised, there's no profile to pivot through.

**Boss mechanic 3 — systemd hardening directives do real work.** `NoNewPrivileges` + `ProtectSystem=strict` + `ProtectHome` + the rest is ~10 extra lines in the unit file that cheaply lock the process to read-only `/`, invisible `/home` and `/root`, no device nodes, no kernel-tunable writes. node_exporter needs none of these so they're free wins.

**Boss mechanic 4 — Prom scrape source IP on lab LXCs.** Scrapes from VPS to `192.168.50.<pihole|wizmood>` arrive via the subnet route from `ts`, so the source IP seen by the target's nftables is `192.168.50.<ts's lease>`, NOT the VPS's tailnet IP. Allow rule must match the lab subnet (`192.168.50.0/24`), not the VPS's `100.113.225.49`.

**Achievement 🏆 "Eyes Across the Lab"** — all five `/metrics` endpoints answer with Prom-format output from the Mac, each `systemctl status node_exporter` is `active (running)`, docker container `Up` on VPS, nftables amendments live on pihole + wizmood.

**Gotchas vault:**
- **Checksum + published sums must both come from the same release URL.** Don't download `sha256sums.txt` from a mirror while the tarball came from GitHub, or vice-versa. Supply-chain verification only works if both sides come from the publisher.
- **`sha256sum -c --ignore-missing` is required** — the published sums file lists hashes for every platform (linux-amd64, darwin-arm64, etc.); without `--ignore-missing`, it errors on every one you didn't download.
- **`systemctl enable --now` first time is fine** — the service wasn't already running, so `--now` actually starts it. Compare to the runbook 06 nftables gotcha where `enable --now` was a no-op because the service was already up.
- **VPS node_exporter container needs `pid: host`** or it only sees its own PID 1 and reports 1 process total. Same for `/proc`, `/sys`, `/` mounts.
- **Proxmox's host firewall layer** (`pve-firewall`) can interact with nftables unpredictably. Skip host-level firewall on HP; the LAN trust boundary is already the real control.
- **Don't try to install node_exporter via apt on Debian 13 LXCs** — Debian's `prometheus-node-exporter` package tracks an older version (v1.6.x range typically). Fine for a lab, but you lose version pinning alignment with the compose stack. Install from upstream release for consistency.

### 🎯 Quest 4 — Wire the Nerves (+80 XP)

*To be fleshed out.* Scrape config under `services/prometheus/`. All node_exporters + chckpoint `/metrics` + Caddy admin as placeholder "down" jobs.

### ⚔️ Mini-boss — "Every light green" (+150 XP)

Prom's `/targets` page shows every job UP. Lab targets scrape via the subnet route, VPS-local targets scrape via the docker network, chckpoint + Caddy are legitimately `DOWN` (you haven't exposed them yet) — but their state is "deliberately down," not "misconfigured down."

**Act I cleared → Journeyman → Monitor Apprentice.** You can walk away for a week.

---

## 🗺️ ACT II — "Make Pictures"

*Visible, no alerts yet. Mistakes here are embarrassing but not pager-worthy.*

### 🎯 Quest 5 — Paint the Walls (+60 XP) ✅

**Goal.** Turn raw Prom metrics into glance-able pictures. Three community dashboards, provisioned from Git (not clicked in via Grafana's Import wizard) so they survive volume loss, diff in review, and deploy consistently.

**Imported.**

| Dashboard | Grafana.com ID | Folder | Status at import |
|---|---|---|---|
| Node Exporter Full | `1860` | `node/` | ✅ live data, 4 hosts across 2 jobs |
| Caddy Monitoring | `20802` | `web/` | 🟡 placeholder — waits on Caddy admin `/metrics`; Loki panels deliberately broken |
| Go Metrics | `10826` | `app/` | ✅ unexpectedly populated — node_exporter + Prom + Grafana + Alertmanager are all Go binaries |

**Moves run.**
1. Fetched 1860 JSON from `grafana.com/api/dashboards/1860/revisions/<rev>/download` (pinned revision, not `latest`, for reproducibility).
2. Normalized the datasource UID — set `uid: prometheus` in `provisioning/datasources/prometheus.yml` so community dashboards' `${DS_PROMETHEUS}` template var resolves against our provisioned Prom without wizard import.
3. Fetched Caddy + Go dashboards, same pattern. Both needed jq fix-up to rewrite baked-in datasource UIDs onto `prometheus` (upstream dashboards carry the exporter's own instance UIDs as artifacts).
4. Deployed: committed JSONs + YAML, pulled on VPS, `docker compose restart grafana`.
5. Verified in browser.

**Boss mechanics encountered.**
- **Datasource UID migration foot-gun.** Adding `uid: prometheus` to an already-provisioned datasource (originally created with an auto-generated UID in Quest 2) halted Grafana startup: the modern provisioner is UID-keyed, so the YAML looked like a new record while the name collided with the old one. Fix: added `deleteDatasources:` block to purge the old record before provisioning. Idempotent — no-op after first run. Fresh installs never hit this; it's pure migration pain.
- **Community dashboard datasource rot.** 1860 ships clean (`${DS_PROMETHEUS}` template var). 20802 and 10826 ship with the original author's instance UIDs baked in (`beok7uikyo1kwf` in Go's case) — all panels fail to resolve without fix-up. `jq` walk-and-rewrite is the one-liner cure; cost is that files no longer round-trip against upstream re-fetches.
- **K8s-biased template vars.** Dashboard 10826 (Go Metrics) uses `namespace` and `pod` template dropdowns for filtering — meaningless on bare-metal. All series render overlaid without filtering. Tolerable for ~6 Go processes; would need an `instance`/`job` rewrite or a swap if we add more Go services. Logged, not fixed.
- **Loki panels remain broken on Caddy.** Deliberate — Loki is out of scope. Caddy is a placeholder dashboard anyway; revisit when Caddy admin metrics are actually live.

**New gotcha (worth remembering):** Grafana datasource YAML changes (including uid) require a full container restart, not just SIGHUP — the provisioner only runs at process start. Dashboard JSON changes, by contrast, are picked up live by the file provisioner's polling loop.

**Realization from the dashboard surfing:** `go_*` metrics flow from every Go binary with `promhttp.Handler()`. Our stack has four Go processes we never thought to "instrument" — Prom, Grafana, Alertmanager, node_exporter — and all of them populate the Go runtime dashboard for free. The observability stack monitors itself before any user app opts in.

---

### 🎯 Quest 6 — Watch Outward (+80 XP)

*To be fleshed out.* blackbox_exporter on a lab LXC (placement TBD). Probe targets:
- **chckpoint public URL** — first "lab watches VPS" link; if the VPS burns down, the lab notices
- **wizmood `:8080` dashboard** — fills the "is wizmood responding" gap left by skipping node_exporter on it in Quest 3

### 🎯 Quest 7 — Count the Queries (+60 XP)

*To be fleshed out.* `eko/pihole-exporter` as sidecar container next to Pi-hole. API wiring for Pi-hole v6 (not v5 — the v6 API gate is a known footgun).

---

## 🗺️ ACT III — "Wake Up for It"

*Phone starts buzzing. Rollback exists but if you break it with the family's wifi dependent on Pi-hole, you'll hear about it.*

### 🎯 Quest 8 — Teach the Oracle to Speak (+150 XP)

*To be fleshed out.* Alert rules: host down, Pi-hole FTL dead, chckpoint 5xx *ratio* (not raw count), TLS cert < 14d, disk > 85%, node load > N for M min. Route everything to one ntfy topic initially.

### ⚔️ Boss — "The Silent Oracle" (+200 XP)

Induce a real alert on purpose — e.g. stop node_exporter on `wizmood` for 5 minutes. Alert should fire, phone should buzz via ntfy, and the alert payload should contain enough context to act on without SSH'ing anywhere. Resolve → recovery notification lands.

If the alert fires but ntfy doesn't ping → webhook config. If ntfy pings but the body is unreadable → templating. If no alert fires at all → the rule's eval window or `for:` clause is wrong.

### 🎯 Quest 9 — Mark the Timeline (+80 XP)

*To be fleshed out.* `lab annotate "message"` wrapper script in `services/grafana/bin/`. Grafana API token with Editor scope. Examples: deploy markers, experiment start/end windows, config changes you want to compare before/after.

### 🎁 Loot collection (+100 XP)

- Add Prom + Grafana + Alertmanager + blackbox + pihole-exporter nodes to `topology.md`
- Changelog entry in `context.md`: stack built, subnet router landed, first alert fired on date X
- Commit everything under `services/prometheus/`, `services/grafana/`, `services/alertmanager/`, plus this runbook
- Achievement 🏆 **"Codified"** — `git status` clean, `main` has the whole arc.

---

## chckpoint-side pattern (NOT this session — reference for later)

When you wire `/metrics` on the chckpoint repo, do it like this:

- **Go backend `/metrics`:** `promhttp.Handler()` mounted on the backend's own router, but **listen on the VPS's tailnet IP, not `0.0.0.0`**. Prom scrapes over the tailnet; the public Caddy frontend never sees `/metrics`.
  - Reason: `/metrics` leaks internals — Go version string, every HTTP route label (which maps your URL space for an attacker), internal histograms with timing side-channels. Tailnet-only is simpler than auth-gating a public endpoint and avoids a whole class of "oops I misconfigured the auth middleware" bugs.
- **Caddy admin endpoint (`:2019`):** same treatment — bind to the tailnet IP in the Caddyfile's `admin` directive. The admin endpoint exposes `/metrics` for Caddy itself (requests, upstream latencies, cert status) and also lets you reload Caddy over HTTP — definitely not public.
- **Prom scrape config stays unchanged** — the placeholder jobs from Quest 4 already target the tailnet IPs; they go from `down` to `up` the moment you deploy the chckpoint change.

## Gotchas carried over (from runbook 06 and earlier)

Reproduced here because they bite again every time:

- **`pct enter` is a non-login shell** — `PATH` missing `/usr/local/bin`. SSH in or source `/etc/profile` manually if a tool "isn't installed."
- **`pct enter` TTY can't drive whiptail** — use SSH, `pct console`, or `script -qc` wrap.
- **`systemctl enable --now` doesn't restart an already-running service** — use `restart` after editing config.
- **`dhclient -r` leaves stale addresses on the interface** — check `ip addr show`, `ip addr del` manually if needed.
- **`tailscale up` is flag-replace, not flag-merge** — always re-pass the full flag set the node already uses.

## Changelog

| Date | Entry |
|---|---|
| 2026-10-21 | Runbook created. Quest 1 (subnet router on `ts`) written and ready to execute; Quests 2–9 stubbed. |
| 2026-11-11 | Quest 1 cleared. `ts` advertises `192.168.50.0/24`, VPS accepts routes (`--accept-routes --ssh`, SSH flag preserved thanks to Tailscale's reset-check), end-to-end verified: `tailscale ping` returns subnet-route pongs, `curl http://192.168.50.5/admin/` returns 302 from VPS. Added gotchas: Tailscale 1.60+ catches the flag-eater; subnet routes live in kernel routing table 52 (not main), so `ip route` alone won't show them; UDP GRO warning is cosmetic at lab scale. `--accept-dns=false` on `ts` preserved Pi-hole as resolver (resolv.conf = `192.168.50.5`, not MagicDNS). |
| 2026-11-14 | Quest 2 cleared. Observability stack live on VPS: `prom/prometheus:v3.16.0`, `grafana/grafana-oss:13.0.2`, `prom/alertmanager:v0.35.0`, all bound to `100.113.225.49` (tailnet IP), all three health endpoints return OK from Mac, `nmap -Pn -p 9090,3000,9093 <vps-public>` reports all three `filtered` (no public leak). Deployed via `vikrant`-user sparse-checkout of `mancave.lab` repo on VPS (deploy key, `services/observability` only). Compose joins `deploy_default` (chckpoint's network, external) so future Prom scrapes of chckpoint work by container name. New gotchas: don't guess image tags — always verify against hub.docker.com's tags API before committing (we burned a round-trip on a plausible-but-fake `grafana/grafana-oss:13.3.1`). Docker group membership = root-equivalent on the host via `/var/run/docker.sock`; `newgrp` refreshes group creds in-place after `usermod -aG`. |
| 2026-11-17 | Quest 4 cleared + Act I mini-boss defeated. `prometheus.yml` wired: 7 live scrape jobs (prometheus self, alertmanager, grafana, node-lab × 3 via Pi-hole hostnames + subnet route, node-vps container) + 2 placeholder jobs (chckpoint-backend, caddy) deliberately DOWN until wired on the chckpoint side. Lab targets use `pve.mancave.lab`/`pihole.mancave.lab`/`ts.mancave.lab` hostnames — Pi-hole circular dependency accepted intentionally (filed as HA DNS Open question). Service discovery tiered as Open questions: Tier 2 (Pi-hole-as-DHCP, auto-generated DNS from leases), Tier 3 (Consul etc.), Tier 1.5 (IaC) — see context.md. **Big new gotcha banked:** bind-mounting a single file + `git pull`-style atomic replace = inode trap. Host path's inode changes but container's bind mount still points at the old inode; SIGHUP then "reloads" the stale content. Signature: `md5sum` mismatch between host and container. Fix: `docker compose restart <service>` after every config pull; `kill -HUP 1` only works on in-place edits that preserve inode (which `git pull` doesn't do). Runbook's Quest 2 boss mechanic 3 updated accordingly. |
| 2026-11-17 | Quest 3 cleared. node_exporter v1.12.1 deployed on 4 of 5 planned hosts: VPS (docker container on `observability_net`), HP/`pve` (systemd + binary, no firewall step), `ts` LXC (systemd + binary), `pihole` LXC (systemd + binary + nftables amendment: `9100` added to existing `dport { 22, 53, 80 }` set). **Wizmood deliberately skipped** — host-level metrics add little value for a Spotify-reactive bulb service; coverage deferred to Quest 6 (blackbox probe against wizmood's `:8080` dashboard) and later service-specific instrumentation. All 4 endpoints return Prom-format output from Mac over the tailnet + subnet route. SHA256 verification baked into the install recipe after retroactive verify on HP's install. New gotchas: `curl` over HTTPS verifies transport only, not content — always `sha256sum -c sha256sums.txt --ignore-missing` BEFORE extract/install; `--no-create-home --shell /usr/sbin/nologin` for service users means zero attack surface beyond the running process's `/proc` entry; systemd `User=`/`Group=` is the only place `node_exporter` user is referenced, and systemd `setuid()`s before `exec()`. Scrape config wiring deferred to Quest 4. |
