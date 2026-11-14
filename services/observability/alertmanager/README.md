# alertmanager

Alertmanager routing + receivers for the VPS. Deployed by the compose stack
in `../observability/`.

Current config is a **skeleton** — all alerts route to a `null` receiver
(logged and discarded). Real routing (ntfy webhook) wired in Quest 8.

Reload in place after editing (no restart):

```
docker exec alertmanager kill -HUP 1
```
