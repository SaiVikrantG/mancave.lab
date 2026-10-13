# mancave.lab: Project Context

Oct 13, 2026 · @Vikrant

## Overview

mancave.lab is a homelab project: turn an old HP laptop into a low-power playground for learning infrastructure engineering, connected to a VPS and phone over Tailscale. The owner already knows Go and wants hands-on practice with virtualization, IaC, monitoring and networking.

**Goals**

- Run the HP laptop as a Type 1 hypervisor (Proxmox preferred) and manage it with code (Terraform/OpenTofu, Ansible, cloud-init, Git)
- Self-host small services (Pi-hole, Uptime Kuma, Jellyfin and similar)
- Extend the existing VPS monitoring stack (Prometheus, Grafana) to cover the lab
- Build Go tools for the lab (exporters, a lab CLI, tsnet services)
- Possibly provision disposable dev VMs for outside users

**How to use this doc in a new chat:** share it as context at the start, treat sections marked unconfirmed as open, and append new decisions to the Changelog at the end. Runbooks are separate files (`runbook_01_*`, `runbook_02_*`, …) kept with this doc; share the relevant one when picking up an operational task.

**Doc workflow note:** this doc and the runbooks live in the project's Git repo. Claude (claude.ai, not Claude Code) can't push directly — it hands back full files or diffs to commit manually. Treat the repo as the source of truth.

## Hardware inventory

Four pieces of hardware are in play, and RAM and storage on the laptop cannot be expanded for now.

| Device | Role | Specs | Notes |
| --- | --- | --- | --- |
| HP Pavilion 15-cs1052tx (5JR96PA) | Lab host, Proxmox VE 9.2 (kernel 7.0.14-23-pve) | Core i7-8565U (4 cores, 8 threads), 8 GB DDR4, 2 TB HDD, NVIDIA GeForce GPU | Ethernet confirmed (Realtek r8169). GPU model still unconfirmed (likely MX150). Internal laptop battery dead — runs on AC only. CMOS coin cell (CR2032) dead — BIOS settings and clock reset on full power loss. AC backed by a home inverter which stands in as UPS. |
| TP-Link TL-WR841N v14 | Spare router, lab router or switch | MT7628NN, 32 MB RAM, 4 MB flash, 2.4 GHz Wi-Fi only, five 10/100 ports | No USB port. OpenWrt not practical on 4/32 hardware, so use stock firmware. Ports are 10/100, the effective ceiling for the lab link regardless of cable grade. |
| Jio AirFiber box | Home internet gateway | 5G wireless, Wi-Fi 6, multiple LAN ports. Home LAN is on 192.168.31.0/24 (gateway likely 192.168.31.1). | LAN port count, speed and USB unconfirmed. Firmware is ISP-locked. Behind CGNAT (carrier-grade NAT) — confirmed as the reason inbound/port-forwarding won't work, independent of any local NAT layering. |
| VPS | Public host, monitoring | Provider and specs not recorded | Runs the owner's own service plus Prometheus and Grafana (being set up). Has a real public IP — candidate as reverse-proxy/bastion front door for any lab service that needs to be public. |
| MacBook (owner's) | Temporary gateway for Proxmox install | Shares Wi-Fi (en0) to USB 10/100 Ethernet dongle (en5) via macOS Internet Sharing; bridge100 = 192.168.2.1/24 | Short-term only. Being fully removed from the HP's network path once the TP-Link is wired in (Ethernet run in progress). |

The owner also has a phone on the tailnet.

## Network and connectivity

The home connection is a Jio AirFiber box behind CGNAT, confirmed to block inbound port forwarding entirely — this holds regardless of how many NAT layers exist locally (single or double NAT makes no difference once CGNAT is already in the path upstream). Tailscale and the VPS are the access strategy, not port forwarding.

**Current temporary layout (install day, still in use as of 2026-10-13)**

1. Jio AirFiber serves the home LAN on 192.168.31.0/24; the MacBook is a Wi-Fi client at 192.168.31.226.
2. The MacBook runs macOS Internet Sharing: Wi-Fi (en0) shared to USB 10/100 Ethernet dongle (en5). This creates bridge100 on the Mac at 192.168.2.1/24, which is the HP's gateway and DNS forwarder.
3. The HP (Proxmox) is wired to the dongle at 192.168.2.2/24, gateway 192.168.2.1, DNS 1.1.1.1.
4. HP traffic path: HP → Mac bridge100 → Mac en0 → AirFiber → internet. Two layers of NAT, no inbound.
5. **Known limitation (still active):** while this layout is in place, the HP has no route to the internet — and therefore no tailnet access — unless the MacBook is actively sharing. The Tailscale LXC built today rides on this same dependency until the direct-wire step below is done.

**Planned layout (double NAT, isolated lab) — Ethernet run in progress**

1. Jio AirFiber box connects to the internet (home subnet 192.168.31.0/24).
2. AirFiber LAN port → TP-Link **WAN port** (not a LAN port — this is what makes the TP-Link route/NAT rather than just switch/bridge).
3. TP-Link serves a separate lab subnet (suggested 192.168.50.0/24) with its own DHCP, LAN IP e.g. 192.168.50.1.
4. TP-Link LAN port → HP's Ethernet port. Bridges do not work over Wi-Fi, so wired is required.
5. The laptop, VPS and phone are reachable from each other over the tailnet.

**TP-Link pre-flight checklist (do before plugging the HP in):**
- Log into TP-Link admin page (check sticker for default IP, typically 192.168.0.1 or 192.168.1.1) from a laptop on one of its LAN ports
- Confirm it's in standard **router mode** (not AP/WISP mode)
- Set LAN subnet (e.g. 192.168.50.1/24) and enable DHCP on that range
- Set WAN to Dynamic IP (DHCP client) so it pulls an address from the AirFiber

**Re-IP needed once wired (not yet done):**
- Proxmox host: currently static 192.168.2.2/24 via vmbr0 → needs new static or DHCP-reserved address in 192.168.50.0/24, gateway 192.168.50.1
- Tailscale LXC (vmid 101): currently static 192.168.2.50/24 → same subnet change needed

**Notes**

- Never enable DHCP on two devices in the same subnet.
- If the AirFiber blocks custom DNS or DHCP, set DNS (for example Pi-hole) on the TP-Link's DHCP instead.
- Reserve a fixed lab address for the Proxmox host.
- Put the AirFiber and TP-Link on the same UPS as the laptop, otherwise a power cut kills connectivity.
- Bridge mode on Jio gear is reported as unreliable or locked down; double NAT is the working approach.
- A router (TP-Link) isn't required for Pi-hole to run, only for every device to *use* it automatically: DHCP is what tells clients which DNS server to use, so Pi-hole needs either the router's DHCP pointed at it, DHCP running on Pi-hole itself (makes it a harder single point of failure), or manual per-device DNS config. Still unconfirmed whether the AirFiber's locked admin page even exposes a custom DHCP DNS setting.
- **Cable spec:** Cat 6 confirmed suitable for the AirFiber→TP-Link and TP-Link→HP runs — the TP-Link's 10/100 ports are the actual ceiling, so Cat 6 is comfortable headroom, not a requirement driven by need. Straight-through (not crossover) is fine; modern NICs auto-negotiate. Main practical concern is physical cable length/slack for wherever the devices end up sitting.
- **Double NAT and inbound, clarified:** double NAT alone would normally complicate port forwarding (forwarding needed at both hops). Moot here because CGNAT upstream already blocks inbound regardless of local NAT layering — confirmed non-issue, not something to solve.

**Making services public without Tailscale (for non-tailnet users):** the home connection's own IP can never be the inbound path (CGNAT), but public exposure is still possible via a front door that isn't the home IP:
1. **VPS as reverse proxy/bastion** — public traffic hits the VPS (real public IP) → forwarded over Tailscale to the HP → HP serves the response. Home IP never exposed. Generalizes beyond the outside-user-VM idea to any lab service.
2. **Tailscale Funnel** — built-in, exposes a local port publicly via Tailscale's relay infra directly, no VPS needed. Simpler, but HTTPS-only/rate-limited and ties exposure to Tailscale's infra.
3. **Cloudflare Tunnel** — `cloudflared` on the HP makes an outbound connection to Cloudflare, which proxies public requests in. No inbound port needed locally either.

## Current state

Proxmox is installed and verified. First LXC (Tailscale) is built, installed, and verified reachable on the tailnet.

- [x] Tailscale tailnet connecting the VPS, the owner's laptop and phone (that laptop is a different device from the HP Pavilion)
- [x] A service of the owner's is hosted on the VPS
- [x] Docker networking between the VPS services was learned in an earlier Claude Code session (stored locally, not searchable from claude.ai chats)
- [x] Proxmox installed on the HP laptop (PVE 9.2-1, kernel 7.0.14-23-pve, ext4, hostname pve.mancave.lab, IP 192.168.2.2/24 via MacBook Internet Sharing — temporary)
- [x] Switched Proxmox repos to no-subscription, ran dist-upgrade, verified KVM + bridge + services
- [x] **Tailscale LXC built and verified** (vmid 101, debian-13-standard, unprivileged): template downloaded, container created with tun/cgroup passthrough, Tailscale installed via signed apt repo (not curl-pipe), `tailscale up` authorized, ping to another tailnet device succeeded round-trip. Tailnet display name shows truncated as `ts` (expected Tailscale behavior — only the first hostname label before the first dot is used; rename via admin console or `tailscale up --hostname=` if desired, not yet done).
- [ ] **Root password / access method not yet set on the Tailscale LXC** — currently only reachable via `pct enter 101` from the Proxmox host (bypasses login via host root privilege). No password set, no SSH configured. Decision pending: quick `passwd` vs. Tailscale SSH (`tailscale up --ssh`, auth via tailnet identity instead of a Linux password).
- [ ] Prometheus and Grafana on the VPS, monitoring the VPS and the hosted service with alerts (in progress)
- [ ] Pi-hole, Uptime Kuma LXCs (held until network re-IP is done; Uptime Kuma has no topology dependency so could go first if desired)
- [ ] Node_exporter + cAdvisor on the lab, scraped by VPS Prometheus
- [ ] HP wired directly to the TP-Link (TP-Link behind the AirFiber), Mac no longer in the path — **in progress, Ethernet run underway as of 2026-10-13**
- [ ] Re-IP Proxmox host and Tailscale LXC onto new lab subnet (192.168.50.0/24) once wired
- [ ] UPS or other power-cut plan (inverter is current stopgap)
- [ ] Replace HP's CMOS coin cell (CR2032)

## Planned architecture

The plan is Proxmox VE on the HP laptop with one or two VMs plus several lightweight LXC containers, all created from code. Proxmox is KVM on Debian, so it counts as Type 1: installing it replaces the laptop's current OS.

**Rough RAM budget (8 GB total)**

| Component | RAM |
| --- | --- |
| Proxmox host | 1 to 1.5 GB |
| VM 1: Docker host (Uptime Kuma, Pi-hole, exporters) | 2 to 3 GB |
| VM 2: disposable practice VM | about 2 GB |
| Headroom | about 1 GB |

Tailscale LXC (vmid 101) is sized separately and small: 1 core, 256 MB RAM, 256 MB swap, 4 GB disk — comfortably outside this VM budget table since it's an LXC, not one of the planned VMs.

**Design choices**

- Prefer LXC (unprivileged) over full VMs where possible; an idle Debian LXC uses roughly 100 to 300 MB
- Use ext4 or LVM-thin; avoid ZFS because its cache consumes RAM
- Keep VM disks small (8 to 15 GB, thin-provisioned) because the 5400 RPM HDD is the bottleneck
- Enable ballooning and a small swap or zram as a safety net
- Use the wired Ethernet port for the bridge (`vmbr0`); put Tailscale in an LXC or VM, or run the host as a subnet router
- Enable VT-x (and VT-d if listed) in the BIOS, set "power on after AC loss" and make the lid-close action "do nothing"
- Set VMs and containers to start on boot with a defined order (DNS first)

**IaC workflow**

1. Build a cloud-init template (Debian or Ubuntu cloud image), by hand first and with Packer later
2. Clone it with OpenTofu or Terraform using the `bpg/proxmox` provider
3. Configure guests with Ansible (Docker, node\_exporter, hardening)
4. Keep everything in Git and practise a full destroy-and-rebuild
5. Back up VMs to the 2 TB HDD with Proxmox backups, and back up configs to the VPS over Tailscale

## Services roadmap

Start with small LXC services, wire them into monitoring, then automate, then go deeper on networking.

1. Install Proxmox on a wired connection; enable VT-x in the BIOS ✓
2. LXCs for Tailscale, Pi-hole and Uptime Kuma — **Tailscale done ✓**; Pi-hole and Uptime Kuma next (Pi-hole held until subnet re-IP, Uptime Kuma has no dependency)
3. Add node\_exporter and cAdvisor on the lab and point the VPS Prometheus at them
4. Rebuild the same services with a cloud-init template, OpenTofu and Ansible
5. Networking practice: VLANs on the Proxmox bridge, then a firewall or router LXC or VM if RAM allows

**Candidate services and projects**

- Monitoring: a second Prometheus or Uptime Kuma on the lab that watches the VPS (so the VPS can be monitored if it dies), Loki for logs, blackbox exporter for probing, smartctl\_exporter for HDD health, and ping probes to graph the AirFiber's latency and uptime
- Network: Pi-hole as tailnet DNS (reachable from the phone), Tailscale subnet router, exit node and ACLs
- Backups: restic or borg from the VPS to the laptop over Tailscale, with tested restores
- Light apps: Vaultwarden, Jellyfin (Intel QuickSync transcoding), Forgejo or Gitea, Home Assistant, Caddy or Traefik as reverse proxy (also candidate for the VPS side, as the public-facing reverse proxy for exposing lab services — see Network section)
- Too heavy for 8 GB: k3s across several VMs, Immich, Nextcloud, local LLMs, Windows VMs, OPNsense as a VM if other VMs are running

## Go project ideas

The suggested first Go project is a Prometheus exporter for something in the lab, because it is small, fits the existing monitoring stack and touches Go, Grafana, the tailnet and Git.

- **Monitoring:** custom Prometheus exporter (`client_golang`) for Proxmox VM status, Pi-hole per-device stats or the VPS service; an endpoint health checker; an Alertmanager webhook forwarder (Telegram, ntfy or Discord)
- **Tooling:** a `lab` CLI with `cobra` wrapping the Proxmox API, Terraform and Ansible; a backup orchestrator that runs and verifies restic; a small Git-pull deploy agent
- **Tailnet:** `tsnet` services that join the tailnet as their own node (internal dashboard, status page, pastebin)
- **Stretch:** a Kubernetes controller (later, once there is a cluster), a custom Terraform provider, a reverse proxy, or a small DNS server with `miekg/dns`
- **Ties to the VM-provisioning idea:** a service that takes a username, provisions a VM, issues access and tears it down after a set time

## Idea: VMs for outside users

The owner may provision ready-to-use dev VMs for people outside the home network. This is an idea under evaluation, not a commitment, and the main design questions are access and isolation.

**Access options**

| Option | How it works | Fit |
| --- | --- | --- |
| Tailscale node sharing | Share one machine with an outside user, restricted by ACLs and tags | Least work; each user needs a Tailscale account |
| VPS as bastion | Users SSH to the VPS, which forwards to their VM over the tailnet | Hides the home IP; one host to harden. Same mechanism now confirmed as the general answer for exposing *any* lab service publicly, not just dev VMs (see Network section). |
| Web IDE | code-server or Coder behind Cloudflare Tunnel or a VPS reverse proxy with auth | Best for non-technical users |
| Per-user WireGuard | Hub on the VPS, one peer config per user (or Headscale) | Most control, most manual |

**Safety rules**

- Use VMs (or unprivileged LXC) on an isolated bridge or VLAN, with no route to the home LAN or the Proxmox management interface
- Set per-VM CPU, RAM, disk and network limits
- Never put the owner's own keys, tokens or Tailscale auth inside user VMs
- Make environments disposable with expiry dates, and monitor them with Prometheus and Grafana
- Check Jio's terms, since consumer plans may restrict hosting for others

With 8 GB of RAM, expect one or two small VMs at a time. Whether the users are trusted friends or strangers is an open question that sets how strict the controls must be.

## Constraints and risks

RAM, disk speed and connectivity are the limits that shape every decision in this project.

- **RAM:** 8 GB, not expandable for now; limits the lab to roughly 2 or 3 small VMs, or many LXCs
- **Storage:** one 2 TB 5400 RPM HDD, not expandable for now; slow for databases, logs and simultaneous VM disk activity
- **Networking:** Ethernet is needed for Proxmox bridging (Wi-Fi bridging does not work); HP Ethernet port confirmed (Realtek r8169)
- **CGNAT:** the Jio connection is confirmed behind carrier-grade NAT — no inbound traffic possible regardless of local NAT setup; use Tailscale, VPS bastion, Funnel or Cloudflare Tunnel for any public access need
- **ISP firmware:** the AirFiber admin page may lock DHCP, DNS and forwarding; the TP-Link is the place to control those
- **TP-Link limits:** 10/100 ports (the actual throughput ceiling for the lab link, cable grade doesn't change this), 2.4 GHz only, 4 MB flash, so it is a lab router or switch, not a platform for Tailscale or OpenWrt packages
- **Power cuts:** home inverter backs the AC and stands in as a UPS as long as it has charge; HP's own laptop battery is dead so it will hard-shutdown the moment inverter + mains both fail. Plan a small UPS and NUT for graceful shutdown, and auto power-on after AC loss (BIOS option not exposed on this Pavilion).
- **Dead CMOS cell:** HP BIOS loses settings (VT-x, boot order) and clock on every full power loss; shows CMOS checksum invalid on boot and clock defaults to Jan 1 2019. Mitigation: avoid full power-off until replaced; NTP corrects clock on each boot. Fix: CR2032 replacement (bottom-panel teardown).
- **Data safety:** one disk with no redundancy, so keep off-box backups on the VPS
- **Single point of failure:** if Pi-hole is the only DNS server and it goes down, the network looks offline
- **Temporary network dependency (still active):** until the TP-Link direct-wire is complete, the HP has no internet (and no tailnet) unless the MacBook is actively sharing
- **No auth on the Tailscale LXC yet:** root has no password; only reachable via `pct enter` from the host. Low risk while LAN-only and host-gated, but should be closed before relying on SSH/remote access to this container.

## Decisions and open questions

The direction is Proxmox on the HP laptop (installed), TP-Link behind the AirFiber for double NAT (Ethernet run in progress) and Tailscale for access (first LXC live).

**Working assumptions (recommended in chat, not yet confirmed by the owner)**

- Proxmox VE chosen and installed (PVE 9.2-1, kernel 7.0.14-23-pve, on 2026-10-12)
- Use the TP-Link in router mode behind the AirFiber for an isolated lab subnet
- Wired Ethernet for the Proxmox host; ext4 chosen at install, no ZFS
- Remote access through Tailscale and the VPS, not port forwarding
- Keep all configuration in Git (repo is the source of truth; Claude in claude.ai hands back files/diffs to commit manually, no direct push)
- First LXC is Tailscale (not Pi-hole), unprivileged, Debian 13 template — **built and verified 2026-10-13**
- Tailscale installed via signed apt repo (matching Proxmox's own repo-signing pattern) rather than the curl-pipe installer script, for consistent package-verification practice

**Open questions**

- [x] Does the HP laptop have a working Ethernet port? Yes, Realtek r8169. GPU model still unconfirmed (couldn't check Device Manager since Windows was wiped — can read it from Proxmox with `lspci | grep -i nvidia` after login).
- [x] Join the HP laptop's Proxmox host or a guest to the tailnet → Done via LXC (vmid 101), not the host directly. Verified reachable, ping round-trip succeeded.
- [ ] How many LAN ports does the AirFiber have, are they gigabit, and is there a USB port (check the model sticker)?
- [ ] VPS provider and specs
- [ ] Buy a UPS, and which size?
- [x] Go straight to Proxmox, or try Debian with Docker and Incus first? → Chose Proxmox directly.
- [ ] For outside-user VMs: trusted friends or strangers, and which access method?
- [ ] Replace the HP's CMOS coin cell (CR2032)?
- [ ] Does the Jio AirFiber's admin page expose a custom DHCP DNS setting? (Determines whether the TP-Link is strictly required for Pi-hole's DHCP auto-config, or just for the general double-NAT isolation goal.)
- [ ] Root password vs. Tailscale SSH for the Tailscale LXC — not yet decided
- [ ] Rename the LXC's tailnet display name from `ts` to something clearer, or leave as-is (cosmetic only)
- [ ] Where should context.md and runbooks live for easiest iteration — Git repo confirmed as source of truth for now; Drive/Claude Doc considered and declined in favor of git-based workflow

## Learning backlog

Topics that came up during the project that we deferred, with enough context to pick up later. Each item has: what triggered it, where to start, what to actually try hands-on.

- **TLS and certificates** — how the TLS handshake works end-to-end (ClientHello/ServerHello, cipher-suite negotiation, ECDHE key exchange), what a certificate contains and how it's verified, the CA trust chain, self-signed vs CA-signed, and how Let's Encrypt's ACME challenges work (HTTP-01, DNS-01, TLS-ALPN-01). *Trigger:* self-signed cert warning on the Proxmox web UI's first login. *Hands-on:* `openssl s_client -connect pve.mancave.lab:8006` to see a live handshake, and `openssl x509 -in /etc/pve/local/pve-ssl.pem -text -noout` on the host to decode its cert. *Suggested reading:* Cloudflare Learning Center for a primer, Ilya Grigorik's *High Performance Browser Networking* (free online) for a solid chapter, Ivan Ristić's *Bulletproof TLS and PKI* for depth.
- **LXC isolation flags (`nesting`, `keyctl`) and device cgroup passthrough** — what `nesting=1` and `keyctl=1` actually unlock/restrict in an unprivileged LXC, why Tailscale needs them, and what the `lxc.cgroup2.devices.allow` / `lxc.mount.entry` lines are doing under the hood to pass `/dev/net/tun` into the container. *Trigger:* creating the first Tailscale LXC (vmid 101), needing these flags and the manual tun device passthrough to get `tailscaled` running in an unprivileged container. *Hands-on:* compare a container's view of `/proc` and cgroups with and without `nesting=1`; inspect `/dev/net/tun` inside the container before and after adding the `lxc.mount.entry` line; read what AppArmor profile Proxmox applies to unprivileged LXCs by default.
- **How Tailscale actually establishes connections through NAT/CGNAT** — STUN-like NAT traversal/hole-punching, DERP relay fallback, and why this works even through CGNAT where manual port forwarding can't. *Trigger:* question about double-NAT/CGNAT breaking inbound access, and confirming Tailscale sidesteps it. *Hands-on:* `tailscale netcheck` to see what kind of NAT/connectivity Tailscale detects for this network; `tailscale ping <peer>` and compare direct vs DERP-relayed latency.
- **Package signing and apt repo trust model** — how GPG-signed apt repos (`Signed-By:`, keyrings) actually verify packages, vs. blindly piping an install script into `sh`. *Trigger:* choosing the signed-repo method over curl-pipe for installing Tailscale. *Hands-on:* inspect `/etc/apt/sources.list.d/tailscale.list` and the keyring file, pull apart what `apt-key`/modern keyring-based verification is doing on install.

## Changelog

Add one row per notable change or decision, newest first, so later chats can see what moved.

| Date | Item | Detail |
| --- | --- | --- |
| 2026-10-13 | Tailscale LXC fully verified | `tailscale up` authorized, `tailscale status` confirmed listing alongside VPS and phone, ping to another tailnet device succeeded round-trip. Tailnet name shows truncated as `ts` (expected: Tailscale uses only the first label before the first dot from the Linux hostname). Rename via admin console or `--hostname` flag, not yet done. |
| 2026-10-13 | Gap identified: no auth on Tailscale LXC | Root has no password (never set at `pct create`); container only reachable via `pct enter` from host (bypasses login via host privilege). Decision pending: quick `passwd` vs. Tailscale SSH (`tailscale up --ssh`). |
| 2026-10-13 | Tailscale installed via signed apt repo, not curl-pipe | Switched from `curl \| sh` installer to adding Tailscale's GPG-signed apt repo directly (same trust model as Proxmox's own repo setup from runbook_02), for consistent package verification across the lab. |
| 2026-10-13 | TP-Link wiring plan confirmed | AirFiber LAN → TP-Link WAN (router mode, not AP/bridge) → TP-Link LAN → HP. Double NAT confirmed as a non-issue for inbound specifically, since CGNAT upstream already blocks that regardless. Cat 6 confirmed as sufficient cable (TP-Link's 10/100 ports are the actual ceiling). Ethernet run in progress as of today. |
| 2026-10-13 | Public-access-without-Tailscale clarified | Home IP can never be an inbound path (CGNAT), but public exposure is still possible via VPS reverse-proxy/bastion, Tailscale Funnel, or Cloudflare Tunnel — all avoid needing the home connection as the front door. VPS bastion approach now understood as general-purpose, not just for the outside-user-VM idea. |
| 2026-10-13 | Doc workflow decided | Context doc and runbooks confirmed to live in the project's Git repo as source of truth. Claude in claude.ai can't push directly — hands back full files/diffs to commit manually. Drive/Claude Doc options considered and declined for now. |
| 2026-10-13 | Tailscale LXC build started | vmid 101, hostname ts.mancave.lab, debian-13-standard template, unprivileged, 1 core / 256 MB RAM / 256 MB swap, local-lvm:4 rootfs, temp IP 192.168.2.50/24 (current Mac-sharing subnet) — to be re-pointed once direct Ethernet is in. `nesting=1,keyctl=1` features plus manual `/dev/net/tun` passthrough added for Tailscale support. Decided to build Tailscale as the first LXC (not Pi-hole) since it unblocks remote access and doesn't depend on final network topology. |
| 2026-10-13 | Clarified: HP has no internet without MacBook sharing | Confirmed the HP's only current route out is through MacBook Internet Sharing; Tailscale (or anything else) on the HP is inert whenever the MacBook isn't actively sharing. Still temporary, resolves once direct Ethernet is in. |
| 2026-10-13 | Clarified: router not strictly required for Pi-hole to run | A router/DHCP server is only needed to get *other devices* to automatically use Pi-hole for DNS; Pi-hole itself can run without one. TP-Link's role is DHCP pointing at Pi-hole (if the AirFiber won't expose that setting itself) or running DHCP on Pi-hole directly (worse for single-point-of-failure risk). |
| 2026-10-12 | Project renamed | Project renamed from "Homely" to "mancave.lab" (matches the Proxmox hostname pve.mancave.lab) |
| 2026-10-12 | Post-install cleanup done | Switched to pve-no-subscription repo (renamed enterprise `.sources` files to `.disabled`), ran `apt dist-upgrade`, verified vmbr0, KVM, pveproxy et al, rebooted into new kernel. Final: PVE 9.2, kernel 7.0.14-23-pve. See runbook_02. |
| 2026-10-12 | Runbooks started | Two runbooks created: `runbook_01_proxmox_install.md` (ISO to USB, BIOS, installer, Mac Internet Sharing gotchas) and `runbook_02_proxmox_post_install.md` (repo switch, dist-upgrade, verification). Convention: separate from this context doc, one per operational task, each with Steps / Verification / Rollback / Gotchas sections. |
| 2026-10-12 | Learning backlog started | New "Learning backlog" section; first entry is TLS/cert deep-dive, deferred from Proxmox web UI first-login self-signed cert warning |
| 2026-10-12 | Proxmox installed on HP | PVE 9.2-1 (May 2026 release), ext4 on full 2 TB HDD, hostname pve.mancave.lab, management IP 192.168.2.2/24 via MacBook Internet Sharing (temporary network setup). BIOS: VT-x enabled, Secure Boot disabled; VT-d and AC-recovery settings not exposed on this Pavilion firmware. |
| 2026-10-12 | HP hardware notes | Ethernet confirmed (Realtek r8169). Dead CMOS cell (CR2032) — BIOS defaults and clock reset to Jan 1 2019 on every full power loss; shows CMOS checksum invalid on boot. Laptop battery dead; AC backed by home inverter acts as UPS. |
| 2026-10-12 | GPU passthrough deprioritised | NVIDIA GPU (likely MX150) passthrough on this laptop is impractical (Optimus wiring, NVIDIA Error 43, IOMMU groups, RAM budget, weak GPU). Future Jellyfin transcoding will use Intel iGPU (QuickSync) passed into an LXC — no VT-d needed. |
| 2026-10-11 | Context doc created | Captured hardware, network plan, Proxmox and IaC plan, services roadmap, Go ideas and the outside-user VM idea from the first planning chat (project was initially named "Homely") |
| 2026-10-11 | Router findings | TP-Link WR841N v14 has no USB and is too small for current OpenWrt; Jio AirFiber likely behind CGNAT |
