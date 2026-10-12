# Runbook 02: Proxmox post-install cleanup

**When to use this:** immediately after a fresh Proxmox VE install, before creating any VMs or LXCs.

**Prereqs:**
- Proxmox installed per runbook 01
- Logged into the web UI as `root`
- Host has internet (through MacBook sharing or direct)

**Expected time:** 15–30 min, mostly waiting on apt.

## Steps

Everything runs in the host's shell. In the web UI: left sidebar → click node (`pve`) → **Shell** at the top.

### 1. Disable enterprise repos

On PVE 9.x these are `.sources` files (new DEB822 format). They don't have an `Enabled:` key by default, so the clean way to disable them is to rename them out of apt's view (apt only reads files ending in `.sources` or `.list`).

```bash
mv /etc/apt/sources.list.d/pve-enterprise.sources /etc/apt/sources.list.d/pve-enterprise.sources.disabled
mv /etc/apt/sources.list.d/ceph.sources /etc/apt/sources.list.d/ceph.sources.disabled
```

### 2. Add the no-subscription repo

```bash
cat > /etc/apt/sources.list.d/pve-no-subscription.sources <<EOF
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: trixie
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF
```

(`trixie` because PVE 9.x is on Debian 13 Trixie. Change if PVE moves to a newer Debian base.)

### 3. Update and dist-upgrade

```bash
apt update
apt dist-upgrade -y
```

`dist-upgrade` not `upgrade` — Proxmox updates often add/remove kernel and QEMU packages that plain `upgrade` would hold back.

### 4. Verify time

```bash
timedatectl
```

Want: `System clock synchronized: yes`, `NTP service: active`, `Time zone: Asia/Kolkata`.

### 5. Verify virtualization

```bash
grep -E 'vmx|svm' /proc/cpuinfo | wc -l
ls -la /dev/kvm
```

Want: non-zero number (on i7-8565U expect 8 or 16 depending on grep), and `/dev/kvm` present with `rw` perms.

If zero: VT-x isn't enabled. Check BIOS. On this HP with the dead CMOS, a full power loss will have reset it.

### 6. Verify network

```bash
ip -br addr
ip route
ping -c 2 1.1.1.1
ping -c 2 deb.debian.org
```

Want: `vmbr0` with the IP you configured at install, default route via the gateway, both pings succeeding.

### 7. Verify Proxmox services

```bash
systemctl is-active pve-cluster pvedaemon pveproxy pvestatd
```

Want: `active` four times.

### 8. Confirm versions

```bash
uname -r      # kernel — e.g. 7.0.14-23-pve on PVE 9.2
pveversion    # e.g. pve-manager/9.2.x/...
```

### 9. Reboot to pick up new kernel

```bash
reboot
```

Web UI drops ~45 sec. Reconnect.

## Verification

After the reboot, logging back into the web UI, going to the node's **Summary** page shows:
- Kernel version matches `uname -r` from step 8
- Load/CPU/RAM graphs populated
- No red error badges in the sidebar

## Rollback / recovery

- If `apt dist-upgrade` fails mid-way: run it again — apt will resume. If a package is persistently broken, `apt install -f` tries to fix dependency state.
- If the host won't boot after kernel upgrade: at the GRUB screen, pick an older kernel from the Advanced boot menu. Then on the running system, investigate and either downgrade the kernel or `apt install proxmox-kernel-7.0` (or current series) to pull a known-good one.
- If network is broken after a change: console into the HP directly (plug a monitor/keyboard into the HP), log in as root, inspect `/etc/network/interfaces` and `ip -br addr` from the physical console.

## Gotchas learned the hard way

- **PVE 9 uses `.sources` (DEB822) files, not `.list`.** Older guides on the internet referring to `/etc/apt/sources.list.d/pve-enterprise.list` are outdated. Check the file extension before `sed`-ing anything.
- **`sed` to disable repos only works if an `Enabled:` key exists.** It usually doesn't in the shipped files, so rename to `.disabled` instead.
- **Linux kernel 7.0 is legitimate for PVE 9.2.** Looks surprisingly high, but Proxmox adopted it as the stable default in May 2026. Not a typo, not a bug.
- **"No valid subscription" popup appears on every login.** Dismiss it, or suppress with the javascript patch — not covered here, look up "proxmox no subscription nag" if it starts to annoy you.
- **Through MacBook Internet Sharing, downloads will be slow** compared to direct wired. If the dist-upgrade feels slow, that's why, not a Proxmox problem.
