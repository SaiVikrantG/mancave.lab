# Runbook 06: pihole — Pi-hole DNS for the lab subnet

**When to use this:** building the `pihole` LXC (vmid 103) from scratch to serve DNS for `192.168.50.0/24`, then cutting the TP-Link DHCP scope over to it so lab names (`pve.mancave.lab`, etc.) resolve on every lab client. Does **not** cover the AirFiber side (`192.168.31.0/24`), tailnet split-DNS, or a VPS replica — those are deliberately out of scope for now.

**Prereqs:**
- Proxmox host up with the TP-Link cutover done (runbooks 01–04)
- Admin access to the TP-Link UI from the Mac (dongle on `192.168.50.x`, or backup Wi-Fi `mancave-lab`)
- Debian 13 LXC template downloaded on the host (`pveam list local`)
- Repo clean on `main`

**Expected time:** 45–60 min.

## Steps

### 1. Create the LXC

On the host Shell:

```bash
pveam list local        # confirm the Debian 13 template filename
pct create 103 local:vztmpl/<debian-13-standard_...>.tar.zst \
  --hostname pihole \
  --cores 1 \
  --memory 512 \
  --swap 512 \
  --rootfs local-lvm:4 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp,firewall=1 \
  --unprivileged 1 \
  --features nesting=0 \
  --onboot 1 \
  --password
pct start 103
```

Notes:
- `--unprivileged 1` means **yes, make it unprivileged** (safer). The default is `0` (privileged). Confusing boolean, worth re-reading.
- `ip=dhcp` is required — without it the container boots with no IP configuration and `eth0` sits up but unaddressed.
- `firewall=1` enables the Proxmox-level firewall hook; it starts permissive. The inside-container nftables in step 6 is a separate, defense-in-depth layer.
- Short hostname `pihole` — matches the convention used by `ts` and `wizmood`. DNS supplies the `.mancave.lab` domain.

### 2. Reserve the LXC's address on the TP-Link

Inside the LXC (via `pct enter 103` or the console):

```bash
ip addr show eth0 | grep 'inet '          # note current DHCP lease
ip link show eth0 | awk '/ether/ {print $2}'   # MAC
```

In the TP-Link UI → DHCP → Address Reservation, add:
- `pihole` → that MAC → **`192.168.50.5`** (outside the `.100–.199` pool)

While there, confirm **`pve → c8:d9:d2:93:53:93 → 192.168.50.10`** is set — this promotes the "planned" HP reservation in `topology.md` to done.

Renew the lease inside the LXC:

```bash
dhclient -r eth0 && dhclient eth0
ip addr show eth0 | grep 'inet '          # should read 192.168.50.5
```

**Gotcha:** `dhclient -r` releases the lease but doesn't always strip the address off the interface. If `ip addr` shows both the old and the new address, drop the old one manually:

```bash
ip addr del 192.168.50.<old>/24 dev eth0
```

### 3. Base updates and SSH

```bash
apt update && apt upgrade -y
apt install -y openssh-server
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
systemctl restart ssh
```

Debian 13's default `PermitRootLogin prohibit-password` only allows SSH key auth. Flipping to `yes` lets you log in with the password you set at container create, which is convenient for the installer step. **Switch back to key-only after this runbook** — see step 10.

From the Mac:
```bash
ssh root@192.168.50.5 'echo ok'
```

### 4. Fix PATH before running the Pi-hole installer

**Gotcha specific to `pct enter`:** `pct enter` gives you a non-login shell that reads `/etc/bash.bashrc` and `~/.bashrc` but **not** `/etc/profile`. On stock Debian, `/usr/local/{sbin,bin}` is added to PATH by `/etc/profile`, so `pct enter` sessions have `PATH=/sbin:/bin:/usr/sbin:/usr/bin` — missing `/usr/local/bin`, which is where `pihole` installs. The result: `pihole: command not found` after a successful install.

Fix once, make it stick:

```bash
echo 'export PATH=/usr/local/sbin:/usr/local/bin:$PATH' >> /root/.bashrc
export PATH=/usr/local/sbin:/usr/local/bin:$PATH
```

SSH sessions get the right PATH automatically (login shell), so if you SSH'd in from the Mac this step is cosmetic. If you'll use `pct enter` later, it matters.

### 5. Install Pi-hole

Download first, then run — do **not** pipe `curl | bash`:

```bash
curl -sSL https://install.pi-hole.net -o basic-install.sh
bash basic-install.sh
```

**Why not `curl | bash`:** the installer uses `whiptail` TUI dialogs. Piping consumes stdin, so whiptail has nowhere to read keystrokes from and sits silently at the first prompt.

**Second gotcha — `pct enter` TTY:** if you're running this from `pct enter` and get `cannot open tty-output`, whiptail needs a proper pty that `pct enter` doesn't provide. Three fixes:
- Wrap in `script`: `script -qc 'bash basic-install.sh' /dev/null`
- Use `pct console 103` from the host instead of `pct enter` (detach with Ctrl-a q)
- SSH in from the Mac (login shell → real tty)

Installer choices:
- Interface: `eth0`
- Upstream DNS: Custom → `1.1.1.1`, `1.0.0.1`
- Blocklists: default on (StevenBlack's unified list is sufficient — resist piling on more lists on day one)
- Install web admin + lighttpd: **yes**
- Log queries: **yes**
- Privacy mode: **0 (show everything)** — single-user lab, don't anonymize your own logs
- IPv6 upstream: **no** — no working v6 end-to-end in this network (CGNAT, TP-Link doesn't do dual-stack); enabling it just adds timeouts on `AAAA` queries
- Static IP in installer: accept whatever it offers — the TP-Link reservation is the real source of truth

Set the admin password after install:

```bash
pihole setpassword
```

Verify:

```bash
pihole status
systemctl is-active pihole-FTL lighttpd
```

**Harmless warning worth knowing:** `Insufficient permissions to set process priority to -10 (CAP_SYS_NICE required)` appears in logs. FTL asks for `nice -10`; unprivileged LXCs don't have `CAP_SYS_NICE`. FTL falls back to normal priority — fine on a lab network.

### 6. Load the lab's DNS records

**Pi-hole v6 trap:** records no longer go in `/etc/pihole/custom.list`. v6 reads them from `/etc/pihole/pihole.toml`'s `dns.hosts` array. Writing to `custom.list` on fresh v6 installs is silently ignored.

Source of truth is `services/pihole/hosts` in the repo. Deploy from the Mac:

```bash
# in the repo root
HOSTS_JSON=$(awk 'NF && $1 !~ /^#/ {printf "\"%s %s\",", $1, $2}' services/pihole/hosts \
             | sed 's/,$//' | sed 's/^/[/;s/$/]/')
ssh root@192.168.50.5 "pihole-FTL --config dns.hosts '$HOSTS_JSON' && pihole reloaddns"
```

Verify from the LXC:
```bash
pihole-FTL --config dns.hosts     # 4 entries
```

Verify from the Mac:
```bash
dig @192.168.50.5 pve.mancave.lab +short       # 192.168.50.10
dig @192.168.50.5 pihole.mancave.lab +short    # 192.168.50.5
```

**Also note:** `pihole restartdns` from v5 was renamed. v6 split it into `pihole reloaddns` (reload DNS config + hosts) and `pihole reloadlists` (reload adlists only). Use `reloaddns` after editing `dns.hosts`.

### 7. Firewall the LXC

Inside the LXC — allow 22/53/80 from the lab subnet only, drop everything else inbound:

```bash
cat >/etc/nftables.conf <<'EOF'
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;

        ct state established,related accept
        ct state invalid drop

        iif "lo" accept

        ip  saddr 192.168.50.0/24 icmp  type { echo-request, destination-unreachable, time-exceeded } accept
        ip6 saddr fe80::/10       icmpv6 type { echo-request, nd-neighbor-solicit, nd-neighbor-advert, nd-router-advert } accept

        ip saddr 192.168.50.0/24 tcp dport { 22, 53, 80 } accept
        ip saddr 192.168.50.0/24 udp dport 53 accept
    }

    chain forward {
        type filter hook forward priority 0; policy drop;
    }

    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF
nft -c -f /etc/nftables.conf && echo "syntax OK"
systemctl restart nftables         # NOT just `enable --now` — see gotcha
nft list ruleset
```

**Gotcha — `enable --now` doesn't reload a running service.** `systemctl enable --now nftables` starts the service only if it wasn't already running. On fresh Debian 13, nftables is already up with an empty ruleset. `--now` is a no-op; the kernel ruleset stays empty. Use `restart` to force a reload after editing the config.

Verify from the Mac — all should succeed:
```bash
nc -zv 192.168.50.5 22
nc -zv 192.168.50.5 53
nc -zv 192.168.50.5 80
```

These should **time out** (silent drop, correct):
```bash
nc -zvw 2 192.168.50.5 443
nc -zvw 2 192.168.50.5 8080
```

### 8. Smoke test before cutting over

Before any lab client depends on Pi-hole, confirm it works when queried directly:

```bash
dig @192.168.50.5 pve.mancave.lab      +short   # 192.168.50.10
dig @192.168.50.5 open.spotify.com     +short   # real IP (upstream forwarding)
dig @192.168.50.5 doubleclick.net      +short   # 0.0.0.0 (blocked)
```

If any fail, stop and debug — nothing in the lab depends on Pi-hole yet, so Phase 2 waits.

### 9. Point TP-Link DHCP at Pi-hole

TP-Link UI → DHCP Settings:
- Primary DNS: `192.168.50.5`
- Secondary DNS: **blank** (or `0.0.0.0` in TP-Link's UI parlance — same thing, means "unset")
- Save

Nothing happens yet. Existing leases keep the old DNS until they expire or are renewed.

Force one client to refresh and confirm end-to-end:

```bash
# Mac (replace enX with the Ethernet interface name — find via `networksetup -listallhardwareports`)
sudo ipconfig set enX BOOTP && sudo ipconfig set enX DHCP
scutil --dns | grep nameserver    # should list 192.168.50.5
dig pve.mancave.lab +short        # no @server — using system resolver → 192.168.50.10
```

Then the wizmood LXC (the real test — real external deps):

```bash
pct exec 102 -- dhclient -r eth0 && pct exec 102 -- dhclient eth0
pct exec 102 -- getent hosts pve.mancave.lab
pct exec 102 -- getent hosts api.spotify.com
pct exec 102 -- getent hosts api.reccobeats.com
```

If all four resolve, Pi-hole is production for wizmood. The bulb keeps pulsing.

### 10. Lock down SSH

Add the Mac's public key, then disable password auth:

```bash
# from the Mac
ssh-copy-id root@192.168.50.5

# on the LXC
sed -i 's/^PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh

# from the Mac — should log in without a password prompt
ssh root@192.168.50.5 'echo key-auth works'
```

This closes the "console-only access" gap the `ts` LXC still has (tracked in `topology.md`).

## Verification

- `pihole status` on the LXC — all services green
- `pihole-FTL --config dns.hosts` — 4 records, no typos
- `dig pve.mancave.lab +short` from the Mac (no `@server`) returns `192.168.50.10`
- `dig doubleclick.net +short` returns `0.0.0.0` from any lab client (blocklist works)
- `nc -zv 192.168.50.5 443` from the Mac times out (nftables drops)
- `pct reboot 103`, wait 20s, DNS resolves again (services survive reboot)
- Pi-hole admin dashboard at `http://192.168.50.5/admin` logs in and shows live queries

## Rollback

If Phase 2 (step 9) misbehaves — TP-Link UI → DHCP → clear Primary DNS or set back to `192.168.31.1` → renew the test client's lease. Lab names stop resolving, but internet works. The Pi-hole LXC stays alive, harmless, and ready to re-cut-over when the issue is understood.

If the LXC itself is wrong, `pct destroy 103` and start over — nothing else in the lab is wired into it unless Phase 2 is done.

## Gotchas

- **`--unprivileged 1` = unprivileged.** `--unprivileged 0` = privileged (the default). Easy to invert.
- **`ip=dhcp` on `--net0`** is not optional. Without it, no IP, no life.
- **`dhclient -r` leaves stale addresses on the interface.** Check `ip addr show` after; manually `ip addr del` if the old one lingers.
- **`pct enter` is a non-login shell.** PATH is minimal; `pihole` won't be found until `.bashrc` adds `/usr/local/bin`.
- **`pct enter` doesn't give whiptail a usable tty.** Use `script -qc`, `pct console`, or SSH.
- **`curl | bash` breaks whiptail installers.** Download first, run second.
- **Pi-hole v6 ≠ v5.** `custom.list` is dead; records live in `dns.hosts` in `pihole.toml`. `restartdns` → `reloaddns`.
- **`systemctl enable --now` ≠ reload.** If a service is already running, `--now` doesn't restart it. Use `restart` to pick up config changes.
- **No IPv6.** AAAA queries without working v6 upstream = timeouts fallback to A, adding latency for no benefit. Leave v6 off.
- **Secondary DNS is a trap.** Setting a public resolver as secondary means clients may hit it unpredictably, bypassing lab-name resolution. With a single Pi-hole and no replica, prefer no secondary — lab-name failures track Pi-hole failures, which track HP failures (which already take down everything else anyway).
- **Admin UI edits to local records write to `pihole.toml`, not to this repo.** They'll be overwritten on next deploy from `services/pihole/hosts`. Edit the file, not the UI.
- **FTL complains about `CAP_SYS_NICE`.** Harmless in an unprivileged LXC — ignore.

## Service pattern recap

```
Mac / wizmood LXC / phone (on mancave-lab Wi-Fi)
          │
          │  DHCP from TP-Link hands out DNS = 192.168.50.5
          ▼
      Pi-hole LXC (vmid 103, 192.168.50.5)
      ├─ Local records (dns.hosts in pihole.toml) → answer directly
      └─ Everything else → forward to Cloudflare (1.1.1.1 / 1.0.0.1)
          │
          ▼
      Internet
```

Rebuild time from a bare LXC: ~20 min with this runbook in front of you, mostly waiting on `apt` and the installer.
