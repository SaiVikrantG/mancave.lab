# mancave.lab: Topology

Living diagram of the homelab's physical and logical wiring. Update whenever the layout changes materially, and add a row to the Changelog in `context.md` so the two stay in sync.

**Conventions**

- Each diagram has an "as of" date and a short note on what's temporary.
- Physical links are solid arrows; overlay/logical links (e.g. Tailscale) are dashed.
- Subnets and fixed IPs are called out on the node or the link.

## Current: double NAT with isolated lab subnet

*As of 2026-10-19. HP, VPS and phone meet on the tailnet; inbound from the internet is not relied on (CGNAT upstream). The install-day MacBook Internet Sharing path is retired — see runbooks 01 and 04 for how we got here. The `wizmood` LXC and its cross-subnet reach to the WiZ bulb landed 2026-10-18, see runbook 05. Pi-hole LXC now serves DNS for the lab (`pve.mancave.lab` and friends resolve on every lab client via TP-Link DHCP) — see runbook 06.*

```mermaid
graph LR
    INET((Internet))
    JIO[Jio AirFiber<br/>192.168.31.0/24<br/>home LAN, CGNAT]
    TPL[TP-Link WR841N v14<br/>WAN: DHCP from AirFiber<br/>LAN: 192.168.50.0/24<br/>router mode + DHCP<br/>Wi-Fi SSID: mancave-lab]
    HP[HP Pavilion<br/>Proxmox VE 9.2<br/>pve.mancave.lab<br/>vmbr0: 192.168.50.10 reserved]
    TSLXC[LXC 101: ts<br/>Tailscale ✓]
    WIZLXC[LXC 102: wizmood<br/>Spotify → WiZ bulb<br/>nftables egress firewall<br/>dashboard :8080<br/>audio-tap UDP :38900]
    PIHOLE[LXC 103: pihole<br/>192.168.50.5 reserved<br/>lab DNS + ad/tracker block<br/>upstream 1.1.1.1/1.0.0.1]
    FUTURE[Future LXCs:<br/>Uptime Kuma,<br/>exporters, Docker host]
    BULB[Philips WiZ bulb<br/>192.168.31.215<br/>UDP :38899]
    VPS[VPS<br/>Prometheus + Grafana<br/>owner's service]
    PHONE[Phone]
    MAC[MacBook<br/>Wi-Fi: 192.168.31.x AirFiber<br/>Ethernet: 192.168.50.x TP-Link<br/>admin workstation]
    HOME[Other home devices<br/>on 192.168.31.0/24]

    INET --- JIO
    JIO --- HOME
    JIO --- BULB
    JIO -- Wi-Fi --- MAC
    JIO -- AirFiber LAN → TP-Link WAN --- TPL
    TPL -- Ethernet --- HP
    TPL -. backup Wi-Fi .- MAC
    HP --- TSLXC
    HP --- WIZLXC
    HP --- PIHOLE
    HP --- FUTURE
    TPL -. DHCP: DNS=192.168.50.5 .- PIHOLE
    INET --- VPS

    WIZLXC -. unicast UDP via NAT .- BULB
    MAC -. audio envelope UDP .- WIZLXC

    HP -. tailnet .- VPS
    HP -. tailnet .- PHONE
    MAC -. tailnet .- VPS
    MAC -. tailnet .- PHONE
    VPS -. tailnet .- PHONE
```

**Notes**

- DHCP runs on the AirFiber for 192.168.31.0/24 and on the TP-Link for 192.168.50.0/24 — never two DHCP servers in the same subnet.
- Home devices on 192.168.31.0/24 cannot reach the lab subnet directly; access from the phone goes over the tailnet.
- The Mac is dual-homed: AirFiber Wi-Fi for everyday internet (192.168.31.x), USB-Ethernet dongle into the TP-Link when lab admin access is needed (192.168.50.x). Service Order on the Mac keeps Wi-Fi as the default internet route so sites still load while plugged into the TP-Link.
- HP reserved at 192.168.50.10 on the TP-Link (MAC `c8:d9:d2:93:53:93`). Pi-hole reserved at 192.168.50.5. Both outside the DHCP pool (.100–.199). Reservations are the source of truth; static configs inside guests are avoided (bit us when the subnet changed — see context changelog 2026-10-14).
- TP-Link must be on its **WAN port** (not a LAN port) for it to actually route/NAT; this bit us during setup.
- **Lab DNS = Pi-hole.** TP-Link DHCP hands out `192.168.50.5` as Primary DNS; Secondary is deliberately blank (single Pi-hole with no replica — a public secondary would be hit unpredictably and break lab-name resolution). Pi-hole holds local records for `pve.mancave.lab`, `pihole.mancave.lab`, `ts.mancave.lab`, `wizmood.mancave.lab`; everything else forwards to Cloudflare. Records are reproducible from `services/pihole/hosts` in the repo. The AirFiber side (192.168.31.x) is unaffected — home devices and the WiZ bulb still use whatever the AirFiber hands them.
- TP-Link's own 2.4 GHz Wi-Fi (SSID `mancave-lab`) is enabled as a backup path to reach `192.168.50.x` from the Mac or phone when no cable is at hand. Not fast (10/100 and 2.4 GHz only), but useful when the dongle isn't plugged in.
- Put the AirFiber, TP-Link and HP on the same inverter/UPS circuit — otherwise a power cut takes connectivity down with the host.
- Double NAT itself isn't a problem for inbound: CGNAT upstream already blocks that regardless of local NAT layering. Cat 6 is sufficient for both runs (TP-Link's 10/100 ports are the actual ceiling).
- **Cross-subnet unicast works, broadcast doesn't.** The `wizmood` LXC (192.168.50.x) reaches the WiZ bulb (192.168.31.215) by unicast UDP on port 38899; the TP-Link NATs the packets out its WAN interface and the bulb replies to the NAT'd mapping. WiZ broadcast discovery to `255.255.255.255` dies at the TP-Link, which is why the bulb's IP is hardcoded in the service config. The home side cannot initiate anything *back* into the lab subnet — same NAT, opposite direction — which is the de facto IoT isolation. Lab → home is wide open, though; a compromised LXC can scan 192.168.31.0/24 freely, hence the `wizmood` LXC's nftables egress whitelist.
- **Audio tap over the lab subnet.** When active, the Mac runs a Python script that reads a BlackHole loopback device and ships a 20 Hz RMS envelope to `wizmood` on UDP 38900. Nothing crosses subnets for this path — Mac must be plugged into the TP-Link via its Ethernet dongle (lab-side) for packets to reach the LXC. 32 bytes/pkt × 20/s ≈ 640 B/s. Rate-limited at the LXC firewall to 60 pkt/s per source.

## Tailnet overlay (logical)

*Independent of physical wiring. Shown separately because the tailnet cuts across whichever physical layout is current. Both the HP host and the `ts` LXC are tailnet peers in their own right — two independent paths into the box.*

```mermaid
graph TB
    subgraph Tailnet
        VPS[VPS]
        PHONE[Phone]
        MAC[MacBook<br/>owner's daily driver]
        TSLXC[LXC 101: ts<br/>on HP Pavilion<br/>verified 2026-10-13<br/>re-IP'd 2026-10-14]
        HP[HP Pavilion host<br/>pve.mancave.lab<br/>joined — see context changelog]
    end

    VPS --- PHONE
    VPS --- MAC
    PHONE --- MAC
    TSLXC --- VPS
    TSLXC --- PHONE
    HP --- VPS
    HP --- PHONE
    HP --- MAC
    TSLXC -. same physical box .- HP

    classDef done stroke:#2a2,stroke-width:2px
    class TSLXC done
    class HP done
```

**Resolved:**

- **Tailscale in an LXC.** Unprivileged `ts` LXC (vmid 101, hostname `ts.mancave.lab`, shows truncated as `ts` on the tailnet — expected Tailscale behavior). Verified via `tailscale status` listing it alongside VPS and phone, and a successful round-trip `tailscale ping` to another peer. Session was re-authed on 2026-10-14 after the subnet cutover temporarily knocked it offline.
- **Tailscale on the HP host itself.** Host is now a first-class tailnet peer in its own right, independent of the `ts` LXC. If the LXC dies, remote access to the host still works — and vice versa. The `same physical box` dashed edge in the diagram is informational: both nodes happen to run on the same hardware but neither depends on the other for tailnet connectivity.

**Still open:**

- **Subnet router.** Now that `192.168.50.0/24` exists, some tailnet node needs to advertise it so other tailnet devices (like the phone) can reach lab services directly by LAN IP rather than needing each service individually joined to the tailnet. Two reasonable candidates:
  - The `ts` LXC advertises the route — keeps the router role out of the host, which stays "just the hypervisor"
  - The HP host advertises the route — simpler, one fewer moving part, uses a node that's already there
  - Pi-hole is now live, which makes the "reach lab IPs from the phone" story concrete — the phone over tailnet can't currently resolve `pve.mancave.lab` either, because the Pi-hole isn't on the tailnet. Split DNS via Tailscale admin → DNS pointing `mancave.lab` queries at `192.168.50.5` is the natural next step, which needs the subnet route first.
- **IP forwarding sysctl.** Whichever node ends up advertising the subnet route needs `net.ipv4.ip_forward=1` and the IPv6 equivalent set. `tailscale up --advertise-routes` doesn't flip the forwarding switch itself — classic gotcha.

**Known gap (not a topology issue, but relevant context):** no root password or SSH is set up on the `ts` LXC yet — only reachable via `pct enter` from the Proxmox host console. The host being on the tailnet directly means this gap is less urgent (you can reach the host via tailnet SSH, then `pct enter` from there) but still worth closing. Tracked in `context.md`.

## Changelog

| Date | Change |
| --- | --- |
| 2026-10-19 | Pi-hole LXC (103, 192.168.50.5) added to the current diagram, with a new dashed "DHCP: DNS=192.168.50.5" edge from TP-Link to the LXC making the service pattern explicit. HP reservation at `.10` promoted from "planned" to done in the HP node label. The "Future LXCs" placeholder trimmed (Pi-hole removed from the list). Notes updated: the earlier "if the AirFiber blocks custom DNS…" entry replaced with a concrete description of the Pi-hole DNS setup — Primary = `.5`, Secondary deliberately blank, local records sourced from `services/pihole/hosts`, AirFiber side unaffected. HP/Pi-hole reservation note consolidated into one line referencing the "don't hardcode in guest configs" lesson. "Still open: subnet router" tightened — Pi-hole landing makes the phone-reaches-lab-DNS question concrete and names split-DNS as the next step. |
| 2026-10-18 | `wizmood` LXC (102) added to current diagram alongside the existing `ts` LXC; previously-unnamed VMs/LXCs block split into three nodes — `ts`, `wizmood`, and "Future LXCs" placeholder. New BULB node on the home subnet (192.168.31.215) with a dashed "unicast UDP via NAT" edge from `wizmood`. New dashed edge from Mac to `wizmood` for the audio-envelope UDP feed. Notes section adds entries explaining cross-subnet unicast vs. broadcast behaviour and the audio-tap packet shape. |
| 2026-10-14 | HP host joined to the tailnet directly — second tailnet node on the box alongside the `ts` LXC. Tailnet overlay updated: HP node promoted from "not yet joined" (dashed/greyed) to a first-class peer with `done` styling; `same physical box` edge kept but reframed as informational rather than a dependency. "Still open: Tailscale on host" removed from the open-items list. Subnet-router question updated to list both candidates (`ts` LXC or HP host) rather than defaulting to the LXC. New gotcha added for `ip_forward` sysctl. |
| 2026-10-14 | TP-Link cutover complete: "Planned" layout promoted to "Current" with as-of 2026-10-14. "Install-day setup via MacBook Internet Sharing" section removed — captured in runbook_01 and runbook_04. HP now on 192.168.50.x via TP-Link DHCP (reservation at .10 planned). `ts` LXC re-IP'd onto 192.168.50.x via DHCP after its hardcoded 192.168.2.50 broke on the subnet change; Tailscale session re-authed after the outage. Mac added to the current diagram as a dual-homed admin workstation (AirFiber Wi-Fi + TP-Link Ethernet). TP-Link backup Wi-Fi path (SSID `mancave-lab`) added. |
| 2026-10-13 | Tailnet overlay updated: Tailscale LXC (vmid 101) added and marked resolved/verified, replacing the old "planned, not yet joined" placeholder for the HP. Install-day diagram updated to show the LXC and flag the MacBook-dependency limitation explicitly. Planned double-NAT diagram annotated: TP-Link WAN port confirmed, re-IP need for both host and LXC noted, double-NAT/CGNAT and Cat 6 clarified as non-issues. New "still open" note added for the subnet-router question (separate from the now-resolved "where does Tailscale run" question). |
| 2026-10-12 | Initial version: install-day setup via MacBook Internet Sharing, planned double-NAT layout, tailnet overlay |
