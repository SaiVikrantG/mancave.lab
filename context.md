# mancave.lab: Project Context

Oct 11, 2026 · @Vikrant

## Overview

mancave.lab is a homelab project: turn an old HP laptop into a low-power playground for learning infrastructure engineering, connected to a VPS and phone over Tailscale. The owner already knows Go and wants hands-on practice with virtualization, IaC, monitoring and networking.

**Goals**

- Run the HP laptop as a Type 1 hypervisor (Proxmox preferred) and manage it with code (Terraform/OpenTofu, Ansible, cloud-init, Git)
- Self-host small services (Pi-hole, Uptime Kuma, Jellyfin and similar)
- Extend the existing VPS monitoring stack (Prometheus, Grafana) to cover the lab
- Build Go tools for the lab (exporters, a lab CLI, tsnet services)
- Possibly provision disposable dev VMs for outside users

**How to use this doc in a new chat:** share it as context at the start, treat sections marked unconfirmed as open, and append new decisions to the Changelog at the end. Runbooks are separate files (`runbook_01_*`, `runbook_02_*`, …) kept with this doc; share the relevant one when picking up an operational task.

## Hardware inventory

Four pieces of hardware are in play, and RAM and storage on the laptop cannot be expanded for now.

| Device | Role | Specs | Notes |
| --- | --- | --- | --- |
| HP Pavilion 15-cs1052tx (5JR96PA) | Lab host, Proxmox VE 9.2 (kernel 7.0.14-23-pve) | Core i7-8565U (4 cores, 8 threads), 8 GB DDR4, 2 TB HDD, NVIDIA GeForce GPU | Ethernet confirmed (Realtek r8169). GPU model still unconfirmed (likely MX150). Internal laptop battery dead — runs on AC only. CMOS coin cell (CR2032) dead — BIOS settings and clock reset on full power loss. AC backed by a home inverter which stands in as UPS. |
| TP-Link TL-WR841N v14 | Spare router, lab router or switch | MT7628NN, 32 MB RAM, 4 MB flash, 2.4 GHz Wi-Fi only, five 10/100 ports | No USB port. OpenWrt not practical on 4/32 hardware, so use stock firmware. |
| Jio AirFiber box | Home internet gateway | 5G wireless, Wi-Fi 6, multiple LAN ports. Home LAN is on 192.168.31.0/24 (gateway likely 192.168.31.1). | LAN port count, speed and USB unconfirmed. Firmware is ISP-locked. Likely behind CGNAT. |
| VPS | Public host, monitoring | Provider and specs not recorded | Runs the owner's own service plus Prometheus and Grafana (being set up). |
| MacBook (owner's) | Temporary gateway for Proxmox install | Shares Wi-Fi (en0) to USB 10/100 Ethernet dongle (en5) via macOS Internet Sharing; bridge100 = 192.168.2.1/24 | Short-term only, until a long Ethernet cable or the TP-Link is in place. |

The owner also has a phone on the tailnet.

## Network and connectivity

The home connection is a Jio AirFiber box that probably sits behind carrier-grade NAT (CGNAT), so inbound port forwarding from the internet should not be relied on; Tailscale and the VPS provide remote access instead.

**Current temporary layout (install day)**

1. Jio AirFiber serves the home LAN on 192.168.31.0/24; the MacBook is a Wi-Fi client at 192.168.31.226.
2. The MacBook runs macOS Internet Sharing: Wi-Fi (en0) shared to USB 10/100 Ethernet dongle (en5). This creates bridge100 on the Mac at 192.168.2.1/24, which is the HP's gateway and DNS forwarder.
3. The HP (Proxmox) is wired to the dongle at 192.168.2.2/24, gateway 192.168.2.1, DNS 1.1.1.1.
4. HP traffic path: HP → Mac bridge100 → Mac en0 → AirFiber → internet. Two layers of NAT, no inbound.

**Planned layout (double NAT, isolated lab)**

1. Jio AirFiber box connects to the internet (home subnet 192.168.31.0/24).
2. A LAN port on the AirFiber goes to the WAN port of the TP-Link WR841N.
3. The TP-Link serves a separate lab subnet (suggested 192.168.50.0/24) with its own DHCP.
4. The Proxmox laptop connects by Ethernet to a TP-Link LAN port. Bridges do not work over Wi-Fi, so wired is required.
5. The laptop, VPS and phone are reachable from each other over the tailnet.

**Notes**

- Never enable DHCP on two devices in the same subnet.
- If the AirFiber blocks custom DNS or DHCP, set DNS (for example Pi-hole) on the TP-Link's DHCP instead.
- Reserve a fixed lab address for the Proxmox host.
- Put the AirFiber and TP-Link on the same UPS as the laptop, otherwise a power cut kills connectivity.
- Bridge mode on Jio gear is reported as unreliable or locked down; double NAT is the working approach.

## Current state

Proxmox is installed and verified; next up is Tailscale and then the monitoring stack.

- [x] Tailscale tailnet connecting the VPS, the owner's laptop and phone (that laptop is a different device from the HP Pavilion)
- [x] A service of the owner's is hosted on the VPS
- [x] Docker networking between the VPS services was learned in an earlier Claude Code session (stored locally, not searchable from claude.ai chats)
- [x] Proxmox installed on the HP laptop (PVE 9.2-1, kernel 7.0.14-23-pve, ext4, hostname pve.mancave.lab, IP 192.168.2.2/24 via MacBook Internet Sharing — temporary)
- [x] Switched Proxmox repos to no-subscription, ran dist-upgrade, verified KVM + bridge + services
- [ ] Prometheus and Grafana on the VPS, monitoring the VPS and the hosted service with alerts (in progress)
- [ ] First LXCs: Tailscale, Pi-hole, Uptime Kuma
- [ ] Node_exporter + cAdvisor on the lab, scraped by VPS Prometheus
- [ ] HP wired directly to the AirFiber (or TP-Link), Mac no longer in the path
- [ ] Lab router (TP-Link) placed behind the AirFiber
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
2. LXCs for Tailscale, Pi-hole and Uptime Kuma
3. Add node\_exporter and cAdvisor on the lab and point the VPS Prometheus at them
4. Rebuild the same services with a cloud-init template, OpenTofu and Ansible
5. Networking practice: VLANs on the Proxmox bridge, then a firewall or router LXC or VM if RAM allows

**Candidate services and projects**

- Monitoring: a second Prometheus or Uptime Kuma on the lab that watches the VPS (so the VPS can be monitored if it dies), Loki for logs, blackbox exporter for probing, smartctl\_exporter for HDD health, and ping probes to graph the AirFiber's latency and uptime
- Network: Pi-hole as tailnet DNS (reachable from the phone), Tailscale subnet router, exit node and ACLs
- Backups: restic or borg from the VPS to the laptop over Tailscale, with tested restores
- Light apps: Vaultwarden, Jellyfin (Intel QuickSync transcoding), Forgejo or Gitea, Home Assistant, Caddy or Traefik as reverse proxy
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
| VPS as bastion | Users SSH to the VPS, which forwards to their VM over the tailnet | Hides the home IP; one host to harden |
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
- **CGNAT:** the Jio connection likely blocks inbound traffic, so use Tailscale and the VPS for access
- **ISP firmware:** the AirFiber admin page may lock DHCP, DNS and forwarding; the TP-Link is the place to control those
- **TP-Link limits:** 10/100 ports, 2.4 GHz only, 4 MB flash, so it is a lab router or switch, not a platform for Tailscale or OpenWrt packages
- **Power cuts:** home inverter backs the AC and stands in as a UPS as long as it has charge; HP's own laptop battery is dead so it will hard-shutdown the moment inverter + mains both fail. Plan a small UPS and NUT for graceful shutdown, and auto power-on after AC loss (BIOS option not exposed on this Pavilion).
- **Dead CMOS cell:** HP BIOS loses settings (VT-x, boot order) and clock on every full power loss; shows CMOS checksum invalid on boot and clock defaults to Jan 1 2019. Mitigation: avoid full power-off until replaced; NTP corrects clock on each boot. Fix: CR2032 replacement (bottom-panel teardown).
- **Data safety:** one disk with no redundancy, so keep off-box backups on the VPS
- **Single point of failure:** if Pi-hole is the only DNS server and it goes down, the network looks offline

## Decisions and open questions

The direction is Proxmox on the HP laptop (installed), double NAT behind the AirFiber (later) and Tailscale for access.

**Working assumptions (recommended in chat, not yet confirmed by the owner)**

- Proxmox VE chosen and installed (PVE 9.2-1, kernel 7.0.14-23-pve, on 2026-10-12)
- Use the TP-Link in router mode behind the AirFiber for an isolated lab subnet
- Wired Ethernet for the Proxmox host; ext4 chosen at install, no ZFS
- Remote access through Tailscale and the VPS, not port forwarding
- Keep all configuration in Git

**Open questions**

- [x] Does the HP laptop have a working Ethernet port? Yes, Realtek r8169. GPU model still unconfirmed (couldn't check Device Manager since Windows was wiped — can read it from Proxmox with `lspci | grep -i nvidia` after login).
- [ ] Join the HP laptop's Proxmox host or a guest to the tailnet (the laptop already on it is a different device)
- [ ] How many LAN ports does the AirFiber have, are they gigabit, and is there a USB port (check the model sticker)?
- [ ] VPS provider and specs
- [ ] Buy a UPS, and which size?
- [x] Go straight to Proxmox, or try Debian with Docker and Incus first? → Chose Proxmox directly.
- [ ] For outside-user VMs: trusted friends or strangers, and which access method?
- [ ] Replace the HP's CMOS coin cell (CR2032)?

## Learning backlog

Topics that came up during the project that we deferred, with enough context to pick up later. Each item has: what triggered it, where to start, what to actually try hands-on.

- **TLS and certificates** — how the TLS handshake works end-to-end (ClientHello/ServerHello, cipher-suite negotiation, ECDHE key exchange), what a certificate contains and how it's verified, the CA trust chain, self-signed vs CA-signed, and how Let's Encrypt's ACME challenges work (HTTP-01, DNS-01, TLS-ALPN-01). *Trigger:* self-signed cert warning on the Proxmox web UI's first login. *Hands-on:* `openssl s_client -connect pve.mancave.lab:8006` to see a live handshake, and `openssl x509 -in /etc/pve/local/pve-ssl.pem -text -noout` on the host to decode its cert. *Suggested reading:* Cloudflare Learning Center for a primer, Ilya Grigorik's *High Performance Browser Networking* (free online) for a solid chapter, Ivan Ristić's *Bulletproof TLS and PKI* for depth.

## Changelog

Add one row per notable change or decision, newest first, so later chats can see what moved.

| Date | Item | Detail |
| --- | --- | --- |
| 2026-10-12 | Project renamed | Project renamed from "Homely" to "mancave.lab" (matches the Proxmox hostname pve.mancave.lab) |
| 2026-10-12 | Post-install cleanup done | Switched to pve-no-subscription repo (renamed enterprise `.sources` files to `.disabled`), ran `apt dist-upgrade`, verified vmbr0, KVM, pveproxy et al, rebooted into new kernel. Final: PVE 9.2, kernel 7.0.14-23-pve. See runbook_02. |
| 2026-10-12 | Runbooks started | Two runbooks created: `runbook_01_proxmox_install.md` (ISO to USB, BIOS, installer, Mac Internet Sharing gotchas) and `runbook_02_proxmox_post_install.md` (repo switch, dist-upgrade, verification). Convention: separate from this context doc, one per operational task, each with Steps / Verification / Rollback / Gotchas sections. |
| 2026-10-12 | Learning backlog started | New "Learning backlog" section; first entry is TLS/cert deep-dive, deferred from Proxmox web UI first-login self-signed cert warning |
| 2026-10-12 | Proxmox installed on HP | PVE 9.2-1 (May 2026 release), ext4 on full 2 TB HDD, hostname pve.mancave.lab, management IP 192.168.2.2/24 via MacBook Internet Sharing (temporary network setup). BIOS: VT-x enabled, Secure Boot disabled; VT-d and AC-recovery settings not exposed on this Pavilion firmware. |
| 2026-10-12 | HP hardware notes | Ethernet confirmed (Realtek r8169). Dead CMOS cell (CR2032) — BIOS defaults and clock reset to Jan 1 2019 on every full power loss; shows CMOS checksum invalid on boot. Laptop battery dead; AC backed by home inverter acts as UPS. |
| 2026-10-12 | GPU passthrough deprioritised | NVIDIA GPU (likely MX150) passthrough on this laptop is impractical (Optimus wiring, NVIDIA Error 43, IOMMU groups, RAM budget, weak GPU). Future Jellyfin transcoding will use Intel iGPU (QuickSync) passed into an LXC — no VT-d needed. |
| 2026-10-11 | Context doc created | Captured hardware, network plan, Proxmox and IaC plan, services roadmap, Go ideas and the outside-user VM idea from the first planning chat (project was initially named "Homely") |
| 2026-10-11 | Router findings | TP-Link WR841N v14 has no USB and is too small for current OpenWrt; Jio AirFiber likely behind CGNAT |
