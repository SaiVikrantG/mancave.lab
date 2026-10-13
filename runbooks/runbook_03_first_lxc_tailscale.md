# Runbook 03: First LXC — Tailscale

**When to use this:** creating the Tailscale LXC on the HP Pavilion's Proxmox host — the first container in the lab, built before the network is finalized so remote access exists as early as possible.

**Prereqs:**
- Proxmox installed and post-install cleanup done (runbooks 01, 02)
- Logged into the Proxmox web UI or host Shell as `root`
- A Tailscale account, and access to authorize a new device (browser on phone or any logged-in device)
- Host has internet (via whatever network path is current — MacBook sharing or direct Ethernet)

**Expected time:** 20–30 min

**Note on timing:** this was built *before* the planned TP-Link/direct-Ethernet network change, deliberately. The container works today on temporary IPs; it needs re-IP'ing once the network topology changes (see Gotchas).

## Steps

### 1. Download the Debian 13 LXC template

Template filenames include a version string that changes over time — always check what's current rather than guessing it.

On the host Shell:

```bash
pveam update
pveam available | grep debian-13
```

Note the exact filename returned (e.g. `debian-13-standard_13.1-1_amd64.tar.zst` — yours may differ).

```bash
pveam download local <exact-filename-from-above>
pveam list local
```

**Check:** `pveam list local` shows the downloaded template file.

### 2. Create the unprivileged LXC

```bash
pct create 101 local:vztmpl/<exact-filename-from-step-1> \
  --hostname ts.mancave.lab \
  --cores 1 \
  --memory 256 \
  --swap 256 \
  --rootfs local-lvm:4 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.2.50/24,gw=192.168.2.1 \
  --nameserver 1.1.1.1 \
  --unprivileged 1 \
  --features nesting=1,keyctl=1 \
  --onboot 1
```

Notes on the values:
- `101` — vmid, arbitrary but must be unique on this host.
- `192.168.2.50/24` / gw `192.168.2.1` — matches the **current temporary** MacBook-sharing subnet. This will need to change once the TP-Link/direct-Ethernet setup is live (see Gotchas).
- `--memory 256 --swap 256` — generous for `tailscaled`, which is small (tens of MB in practice). Swap is a safety net, not an expectation of regular use.
- `local-lvm:4` — 4 GB root disk on the LVM-thin pool (thin-provisioned, won't consume 4 GB immediately).
- `--unprivileged 1` — matches the project's LXC-over-VM, unprivileged-by-default design choice.
- `--features nesting=1,keyctl=1` — required for Tailscale to run cleanly in an unprivileged container. *(Added to the learning backlog — what these actually unlock is not yet understood in depth.)*
- `--onboot 1` — container auto-starts when the Proxmox host boots.

### 3. Pass through the TUN device

Unprivileged LXCs don't expose `/dev/net/tun` by default, which `tailscaled` needs. Add these lines to the container's config **on the host**, before starting it:

```bash
echo "lxc.cgroup2.devices.allow: c 10:200 rwm" >> /etc/pve/lxc/101.conf
echo "lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file" >> /etc/pve/lxc/101.conf
```

**Check:**

```bash
pct config 101
```

Confirm both `lxc.*` lines appear at the bottom, alongside the `features: nesting=1,keyctl=1` line from creation.

If the container was already started before adding these lines, stop it first (`pct stop 101`) — LXC config changes like this need a restart to take effect.

### 4. Start and verify networking

```bash
pct start 101
pct enter 101
```

Inside the container:

```bash
ip -br addr
ping -c 2 1.1.1.1
```

**Check:** `eth0` shows the configured IP (`192.168.2.50/24` if following this runbook as-is), and the ping succeeds — confirms the container is routing out through the host's current network path.

### 5. Install Tailscale via signed apt repo (not curl-pipe)

The one-liner `curl -fsSL https://tailscale.com/install.sh | sh` works, but piping an installer straight into a root shell isn't the most rigorous option available. Debian's normal signed-repo mechanism (the same pattern used for Proxmox's own repos in runbook_02) gives per-package signature verification going forward, not just a one-time trust decision.

Still inside the container:

```bash
apt update
apt install -y curl gnupg
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list
apt update
apt install -y tailscale
```

(`trixie` matches Debian 13, consistent with the host and the LXC template. Adjust if Tailscale's repo structure changes or a different Debian release is used.)

### 6. Authorize and verify

```bash
tailscale up
```

This prints a URL — open it on any device already logged into your Tailscale account to authorize this node.

```bash
tailscale status
```

**Check:** the container appears in the list alongside existing tailnet devices (VPS, phone, etc.), each with a `100.x.x.x` Tailscale IP.

From this container, ping another device already on the tailnet:

```bash
tailscale ping <other-device-name-or-ts-ip>
```

**Check:** a successful round-trip ping confirms the tailnet path works end-to-end, not just that the daemon started.

## Verification

- `pct config 101` shows the tun passthrough lines and `nesting=1,keyctl=1`
- `ip -br addr` inside the container shows the expected `eth0` IP
- `tailscale status` lists this device alongside other tailnet peers
- A ping to another tailnet device succeeds round-trip

## Rollback / recovery

- **Container won't start after adding tun passthrough lines:** check `/etc/pve/lxc/101.conf` for typos in the two `lxc.*` lines; a malformed config line will fail the start. `pct start 101` will surface the error.
- **`tailscaled` fails to start / can't open `/dev/net/tun`:** confirm step 3's lines actually landed (`pct config 101`) and that the container was restarted after adding them, not just left running from before.
- **Full redo:** `pct stop 101 && pct destroy 101` removes the container cleanly; re-run from step 2 (template from step 1 doesn't need re-downloading).
- **Lost tailnet auth / need to re-authorize:** `tailscale logout` then `tailscale up` again inside the container.

## Gotchas learned the hard way

- **Template filenames aren't static strings.** The version segment (e.g. `13.1-1`) changes as Proxmox re-cuts templates — always `pveam available | grep debian-13` first rather than reusing an old filename from a guide or a previous session.
- **Unprivileged LXCs need manual TUN device passthrough.** `--features nesting=1,keyctl=1` alone is not enough for Tailscale — the `/dev/net/tun` cgroup allow + mount entry lines in step 3 are also required, and must be added before (or with a restart after) first start.
- **No root password was set.** `pct create` was run without `--password`. This wasn't a blocker because `pct enter` from the host bypasses normal login (host root privilege), but it means there's currently no way to log into this container except through the Proxmox host itself — no SSH, no console login. **Still open as of this writing** — decide between a quick `passwd` or switching to Tailscale SSH (`tailscale up --ssh`, authenticates via tailnet identity instead of a Linux password) before relying on remote access to this container.
- **Tailnet display name truncates to the first hostname label.** Set `--hostname ts.mancave.lab` at creation, but Tailscale only uses the portion before the first dot (`ts`) as the device name on the tailnet — this is expected behavior (Tailscale appends its own suffix), not a misconfiguration. Rename via the Tailscale admin console or `tailscale up --hostname=<name>` if a clearer name is wanted.
- **This container's IP is temporary and network-topology-dependent.** `192.168.2.50/24` matches the current MacBook-Internet-Sharing subnet. Once the TP-Link is wired in directly (see context.md's Network section), both the Proxmox host and this container need re-IP'ing onto the new lab subnet (planned `192.168.50.0/24`). Until the host itself has an independent route to the internet, this container's tailnet reachability depends entirely on the MacBook actively sharing its connection — closing the laptop lid drops this container off the tailnet too.
- **Prefer the signed apt-repo method over curl-pipe where practical.** Not unique to Tailscale — same reasoning applies to any future installs in this lab. The repo method costs a few more lines but gives ongoing package-signature verification rather than a one-time trust-the-script moment.
