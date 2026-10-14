# Runbook 04: TP-Link behind AirFiber, HP cutover from MacBook sharing

**When to use this:** moving the lab off the temporary MacBook Internet Sharing path onto the planned double-NAT layout — TP-Link WR841N as a router behind the Jio AirFiber, with the HP on a dedicated lab subnet (192.168.50.0/24).

**Prereqs:**
- TP-Link WR841N v14 powered on, factory-settable
- One Ethernet cable from AirFiber to TP-Link WAN
- One Ethernet cable from TP-Link LAN to HP
- Mac with USB-Ethernet dongle for TP-Link admin access
- HP currently reachable (via Mac sharing per runbook 01), with the install's static config at 192.168.2.2
- Known: HP NIC MAC address (`c8:d9:d2:93:53:93` on this unit)

**Expected time:** 45–90 min including Tailscale LXC recovery.

## Steps

Order matters — configure the TP-Link in isolation first, then do the HP cutover.

### 1. Factory reset the TP-Link (if its state is unknown)

Hold **Reset** on the back ~10 sec until the lights blink. Safe default; you don't know what state it's in.

### 2. Connect Mac to TP-Link LAN (not WAN)

- Unplug the USB-Ethernet dongle from the HP, plug it into one of the **yellow LAN ports** (1–4) on the TP-Link.
- Leave the **blue WAN port empty** for now.
- Mac should pick up `192.168.0.x` from the TP-Link.

The HP goes offline temporarily — fine, you're about to move it anyway.

### 3. Keep Mac internet alive via Wi-Fi

The Ethernet port now connects only to the TP-Link (no internet yet). Turn Wi-Fi back on so the Mac has both:

- **Ethernet** → TP-Link admin (`192.168.0.x`, no internet)
- **Wi-Fi** → AirFiber (internet)

If sites don't load, fix the service order so Wi-Fi is used for internet:

System Settings → Network → ⋯ menu → **Set Service Order** → drag **Wi-Fi above the USB adapter** → Apply.

### 4. Log into the TP-Link admin page

- Browser → `http://192.168.0.1` (or `http://tplinkwifi.net`)
- Default login: `admin` / `admin` — first login forces a password change. Save it to the password manager.

### 5. Configure LAN

**Network → LAN** (or **Advanced → Network → LAN** depending on firmware):

- IP Address: `192.168.50.1`
- Subnet Mask: `255.255.255.0`
- Save. The admin page at the old `192.168.0.1` becomes unreachable immediately.

### 6. Renew Mac's DHCP lease to get on the new subnet

The Mac is still holding its old `192.168.0.x` lease. Force a refresh:

```bash
sudo ipconfig set en5 DHCP
sleep 10
ifconfig en5 | grep "inet "
```

Want: `inet 192.168.50.x`. If still on the old IP after 30 sec, unplug/replug the Ethernet to force a fresh request.

Reconnect to admin at **`http://192.168.50.1`**.

### 7. Configure WAN

**Network → WAN** (or **Internet**):

- Connection Type: **Dynamic IP** (DHCP)
- Save. WAN port is still empty, so it'll show "no connection" — fine.

### 8. Confirm LAN DHCP is on

**DHCP → DHCP Settings**:

- DHCP Server: **Enable**
- Default pool is fine (usually `.100–.199`).

### 9. (Optional) Decide what to do with TP-Link Wi-Fi

**Wireless → Wireless Settings**. Three sensible choices:

- **Disable the radio** — reduces 2.4 GHz noise, cleanest option. Only works if you'll always have Ethernet access to admin stuff.
- **Enable with a different SSID** (e.g. `mancave-lab`) — lets the Mac/phone reach `192.168.50.x` wirelessly as a backup when no cable is around. Can't be on both this and AirFiber Wi-Fi at the same time (one Wi-Fi radio on the Mac), but easy to switch.
- **Leave default on** — fine but noisy, and no reason to.

Backup Wi-Fi (middle option) is what the setup landed on in practice.

### 10. Plug in the WAN

Take the AirFiber Ethernet cable → **blue WAN port** on the TP-Link.

Wait ~30 sec. **Status** page:

- WAN IP: should be `192.168.31.x` (from the AirFiber)
- Gateway: `192.168.31.1` or similar

### 11. Verify internet through the TP-Link

From the Mac (still wired):

```bash
ping -c 2 1.1.1.1
curl -I https://deb.debian.org
```

Both should work. If yes: TP-Link is routing. Internet from this subnet now goes **HP/Mac → TP-Link → AirFiber → internet** (double NAT).

### 12. Switch HP from static (192.168.2.x) to DHCP

Before unplugging the HP from the Mac dongle, change its network config so it comes up correctly on the new subnet.

Console into the HP one last time via Mac sharing. The install leaves `/etc/network/interfaces` looking like:

```
auto lo
iface lo inet loopback

iface nic0 inet manual

auto vmbr0
iface vmbr0 inet static
        address 192.168.2.2/24
        gateway 192.168.2.1
        bridge-ports nic0
        bridge-stp off
        bridge-fd 0

iface nic1 inet manual

source /etc/network/interfaces.d/*
```

Edit the `vmbr0` block to use DHCP:

```
auto vmbr0
iface vmbr0 inet dhcp
        bridge-ports nic0
        bridge-stp off
        bridge-fd 0
```

(Delete the `address` and `gateway` lines, change `static` to `dhcp`, keep the three `bridge-*` lines.)

### 13. Reboot and move the HP

```bash
reboot
```

While it reboots, do the physical move:

1. Unplug HP's Ethernet from the Mac's USB dongle.
2. Plug it into a yellow LAN port on the TP-Link.

### 14. Find the HP's new IP

Easiest: TP-Link admin → **DHCP → DHCP Clients List**. Look for hostname `pve` or the HP's NIC MAC (`c8:d9:d2:93:53:93`). Note the IP.

Web UI: `https://<new-HP-IP>:8006`.

### 15. Fix any LXCs with hardcoded 192.168.2.x addresses

Any LXC/VM that was created while the HP was on 192.168.2.x and given a **static** IP will come up with the wrong address and no route out — including the Tailscale LXC (`ts`) created in runbook 03.

Enter the container from the HP shell:

```bash
pct list                   # find the LXC ID (e.g. 101 for ts)
pct enter 101
ip -br addr                # likely shows eth0 on old subnet
cat /etc/network/interfaces
```

If `eth0` has `inet static` with an address in `192.168.2.0/24`, switch to DHCP:

```
auto eth0
iface eth0 inet dhcp
```

Then:

```bash
ifreload -a                # or systemctl restart networking
ip -br addr                # confirm 192.168.50.x
ping -c 2 1.1.1.1          # confirm internet
```

For the Tailscale LXC specifically, after getting internet back:

```bash
tailscale status           # may show "You are logged out" after a long outage
tailscale up               # follow the login URL on the Mac to re-auth if needed
```

### 16. Reserve a static DHCP lease for the HP

So the HP always gets the same IP without having to hardcode it on the Proxmox host:

TP-Link admin → **DHCP → Address Reservation** → Add:

- MAC: `c8:d9:d2:93:53:93`
- IP: `192.168.50.10` (or any address outside the DHCP pool)
- Save

Same can be done for the `ts` LXC (grab its MAC from Proxmox UI → ts → Network). Reboot the containers/host to pick up the reserved IPs.

### 17. Retire MacBook Internet Sharing

Mac: System Settings → General → Sharing → **Internet Sharing** → off. Not needed anymore.

### 18. (Recommended) Install Tailscale on the Proxmox host itself

Right now tailnet access to the HP goes *through* the `ts` LXC. If that LXC dies, remote access breaks. Belt-and-braces fix: install Tailscale on the host too, so the HP shows up on the tailnet as its own node.

On the HP shell:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
```

Follow the printed URL on the Mac to approve.

## Verification

- `ping 192.168.50.1` from HP → TP-Link reachable
- `ping 1.1.1.1` from HP → internet via TP-Link → AirFiber
- `https://<HP-IP>:8006` loads from Mac over wired Ethernet
- `tailscale status` from Mac shows `ts` (and host if installed) as **online**, not offline
- MacBook Internet Sharing is off, HP still reachable
- TP-Link **DHCP Clients List** shows `pve` with the reserved IP after an HP reboot

## Rollback / recovery

If the HP ends up unreachable after the move, the cleanest recovery is a direct console: plug a monitor + keyboard into the HP, log in as root, inspect:

```bash
ip -br addr
ip route
cat /etc/network/interfaces
```

If no DHCP lease was obtained, suspect the cable, wrong TP-Link port, or TP-Link DHCP not actually enabled. The old config can be restored by setting `vmbr0` back to static on `192.168.2.2/24` and plugging back into the Mac dongle — the Mac sharing setup from runbook 01 still works as a fallback.

For a lost `ts` LXC Tailscale session, the fastest path is the HP console: `pct enter <id>`, confirm networking, re-run `tailscale up` and reauth.

## Gotchas learned the hard way

- **Changing the TP-Link LAN subnet immediately breaks the admin page you're on.** The Mac keeps its old lease and can't reach the new address until DHCP is renewed. `sudo ipconfig set en5 DHCP` is faster than unplugging the cable.
- **The Mac can be on Ethernet (TP-Link admin) and Wi-Fi (AirFiber internet) at the same time.** Service Order controls which gets internet-bound traffic — put Wi-Fi above the Ethernet adapter or sites may try to go out the wrong interface.
- **Only one Ethernet cable + one dongle means a juggling act.** The dongle is needed for TP-Link admin *and* for the HP; the HP goes offline during the admin phase, which is expected because it's about to be moved anyway.
- **LXCs with hardcoded IPs on the old subnet break silently on the move.** The `ts` LXC's `eth0` was `inet static 192.168.2.50/24` from install day and became unreachable after cutover. Default to DHCP for all guests; use TP-Link address reservations for stability instead of static container config.
- **Tailscale will log the LXC out after a long enough disconnect.** Signature: `tailscale status` says `You are logged out` and tries IPv6. Fix: get IPv4 internet back, then `tailscale up` and reauth.
- **The TP-Link's Wi-Fi is 2.4 GHz only, ~100 Mbps.** Fine as backup admin access, bad as a daily Wi-Fi. Use a different SSID (e.g. `mancave-lab`) so you only connect when you need to.
- **`pve.mancave.lab` does not resolve across subnets.** Browser bookmarks to the hostname break; use the IP, or set up proper DNS (Pi-hole LXC on the lab subnet) later. This is on the open-questions list, not fixed yet.
- **Bridge mode on the Jio AirFiber is reportedly locked down** — don't try to eliminate the double NAT by bridging the AirFiber. The TP-Link doing NAT on the lab side is the working arrangement.
