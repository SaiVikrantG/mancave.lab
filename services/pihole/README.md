# services/pihole

Reproducible config for the Pi-hole LXC (vmid 103, `192.168.50.5`) that serves DNS for the lab subnet.

**Source of truth:** `hosts` in this directory. Everything else about Pi-hole (blocklists, upstream resolver, admin password, privacy level) is set once via the installer or the `pihole` CLI and does not need to be tracked here.

## What's here

- `hosts` — local DNS records for the lab (`pve.mancave.lab`, etc.), one record per line. Format: `<ip> <hostname>`.
- `README.md` — this file.

## Pi-hole v6 note

Pi-hole v6 moved local DNS records from `/etc/pihole/custom.list` (plain hosts file) into `/etc/pihole/pihole.toml`'s `dns.hosts` TOML array. The old file still exists on disk but isn't wired into dnsmasq on fresh v6 installs — writing to it does nothing. All deploys below go through `pihole-FTL --config dns.hosts`.

## Deploy

From the repo root on the Mac:

```bash
# Build the dns.hosts JSON array from hosts, excluding comments/blank lines.
HOSTS_JSON=$(awk 'NF && $1 !~ /^#/ {printf "\"%s %s\",", $1, $2}' services/pihole/hosts \
             | sed 's/,$//' | sed 's/^/[/;s/$/]/')

ssh root@192.168.50.5 "pihole-FTL --config dns.hosts '$HOSTS_JSON' && pihole reloaddns"
```

Verify from any lab client:

```bash
dig @192.168.50.5 pve.mancave.lab +short       # expect 192.168.50.10
dig @192.168.50.5 pihole.mancave.lab +short    # expect 192.168.50.5
```

## Edits via the admin UI

The admin dashboard (Settings → Local DNS Records) writes directly to `pihole.toml`. Those edits will be **overwritten** the next time this file is deployed. Treat the UI as read-only for records — add them here and redeploy.

## Rollback

```bash
ssh root@192.168.50.5 "pihole-FTL --config dns.hosts '[]' && pihole reloaddns"
```

Clears every local record. Pi-hole falls back to pure upstream resolution for lab names (which won't resolve, since nothing public serves `mancave.lab` — this is the point of the whole thing).
