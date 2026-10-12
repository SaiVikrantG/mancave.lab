# Runbook 01: Install Proxmox VE on the HP Pavilion

**When to use this:** installing (or reinstalling) Proxmox VE on the HP Pavilion 15-cs1052tx, from a fresh disk.

**Prereqs:**
- Proxmox VE ISO (currently 9.2-1, grab latest from https://www.proxmox.com/en/downloads)
- USB stick ≥ 2 GB (anything on it will be wiped)
- MacBook with a USB-to-Ethernet dongle, Ethernet cable to the HP, or a long enough Ethernet cable to the AirFiber/TP-Link
- HP backed up — install wipes the whole 2 TB HDD

**Expected time:** 60–90 min (first time, with reading)

## Steps

### 1. Write the ISO to USB (on the MacBook)

Etcher currently fails on Proxmox ISOs with `(0, h.requestMetadata) is not a function`. Use `dd` instead.

```bash
# Find the USB device
diskutil list external

# Unmount (don't eject — unmount keeps the device node available)
diskutil unmountDisk /dev/diskN

# Write (note the 'r' in rdisk, that's raw mode and much faster)
sudo dd if=~/Downloads/proxmox-ve_X.Y-Z.iso of=/dev/rdiskN bs=1m status=progress

# Eject when done
diskutil eject /dev/diskN
```

Replace `N` with the actual disk number. If macOS pops up "The disk you inserted was not readable by this computer", click **Eject** (NOT Initialize) — that popup is the expected outcome.

### 2. BIOS settings on the HP

Power on, tap **Esc** repeatedly for the startup menu, then **F10** for BIOS Setup.

Under **System Configuration**:
- **Virtualization Technology (VTx)** → Enabled

Not exposed on this Pavilion's BIOS (don't bother hunting):
- VT-d (fine for now; needed only for PCI passthrough)
- "After Power Loss" / "AC Recovery"
- Lid-close action

Also:
- **Secure Boot** → Disabled (BIOS will ask you to type a 4-digit confirmation code to confirm — enter it blind, no display)

Set the system clock to current IST (BIOS format MM/DD/YYYY, 24-hour) — the dead CMOS cell means it resets to Jan 1 2019 every full power-off, and a 7-year-off clock can confuse the installer.

**F10** → Save and Exit.

### 3. Boot from USB

On reboot, tap **Esc** → **F9** for Boot Device Options. Pick the USB. Proxmox blue screen → **Install Proxmox VE (Graphical)**.

### 4. Network: MacBook Internet Sharing (temporary setup)

If using the MacBook as a temporary gateway:

- System Settings → General → Sharing → Internet Sharing (details with the (i)).
- "Share your connection from": **Wi-Fi**
- "To computers using": tick **the specific USB adapter** that matches your dongle (e.g. "USB 10/100 LAN"). macOS lists multiple candidates — pick the one matching the dongle you're actually plugging in.
- Toggle Internet Sharing off, confirm, then on again.

**Verify from the Mac** that sharing attached to the right interface — macOS Internet Sharing silently sticks to the wrong interface sometimes:

```bash
ifconfig en5   # or whichever interface is your dongle
# want: inet 192.168.2.1 ... (or wherever bridge100 lives)
# NOT: inet 169.254.x.x (that's self-assigned, means sharing isn't attached)

ifconfig bridge100
# want: en5 listed as a member
```

If sharing attached to the wrong NIC, re-tick the right one and toggle off/on again. May take a reboot in stubborn cases.

### 5. Proxmox installer

- EULA → I agree
- Target disk → the 2 TB HDD. **Options → Filesystem: ext4** (NOT zfs — ARC eats RAM). hdsize: leave default (full disk, shows as ~1863 GiB because binary vs decimal units).
- Location: Country **India** → sets Asia/Kolkata and US keyboard.
- Password: strong, save to password manager immediately. Email: real email.
- Network:
  - Management interface: **nic0** (the Realtek r8169 — the green dot = link up; iwlwifi is the Wi-Fi, don't pick that)
  - Hostname (FQDN): must have a dot, e.g. `pve.mancave.lab`
  - IP: `192.168.2.2/24` (if using MacBook sharing)
  - Gateway: `192.168.2.1`
  - DNS: `1.1.1.1`
- Summary → review carefully → **Install**. 5–15 min on the 5400 RPM HDD.

### 6. First login

- Pull USB on reboot.
- From the Mac: `https://192.168.2.2:8006` → accept self-signed cert warning → log in as `root` with the install password, realm **Linux PAM standard authentication**.
- Dismiss the "No valid subscription" popup.

### 7. Post-install → go to runbook 02

Repo switch + dist-upgrade + verification is covered in `runbook_02_proxmox_post_install.md`.

## Verification

After install, console on the HP shows the login prompt with the URL. From the Mac, web UI loads at `https://192.168.2.2:8006` with the Proxmox dashboard after login.

## Rollback / recovery

Rollback = reinstall. Nothing in Proxmox install is reversible in-place; the HP's previous Windows is gone the moment the installer finishes partitioning.

If install fails mid-way: reboot, boot from USB again, start over. The partial install does no harm.

## Gotchas learned the hard way

- **Etcher fails on Proxmox ISOs** with `(0, h.requestMetadata) is not a function`. Use `dd` or Raspberry Pi Imager.
- **macOS Internet Sharing silently picks the wrong NIC.** It defaults to internal virtual NICs (en2/en3) rather than the external USB dongle (en5). Check `ifconfig bridge100` lists the right interface as a member; if not, re-tick the right one and toggle off/on.
- **HP Pavilion BIOS does not expose VT-d, AC-recovery, or lid-close action.** Don't waste time hunting.
- **CMOS cell is dead on this HP** — BIOS defaults and clock reset on every full power loss. "CMOS checksum invalid" message + Jan 1 2019 date = this. Replace the CR2032 (bottom-panel teardown) when convenient. Until then, avoid fully powering the HP off, and expect to re-enable VT-x in BIOS if power is ever fully cut.
- **Laptop battery is dead on this HP** — AC only, no stopgap. Home inverter stands in as UPS.
- **Hostname needs a dot.** Just `pve` is invalid; `pve.something.something` works. The Summary screen only shows the short hostname (before the first dot), that's a display thing, not a bug.
- **Install disk shows ~1863 GiB for a 2 TB drive.** Decimal (manufacturer) vs binary (OS) units. Normal.
- **Secure Boot confirmation code is entered blind.** Four digits, no echo, then Enter. If mistyped, HP will ask again.
