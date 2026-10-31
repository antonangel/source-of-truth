# DNS and proxy runbook

Pi-hole answers on 192.168.1.2 (pihole.lan). The LAN is 192.168.1.0/24 and the router is 192.168.1.1.
The admin UI is at http://192.168.1.2:8080/admin.

After editing local records, restart DNS:

```bash
cd /srv/stack/dns
docker compose pull   # update images first
docker compose up -d pihole
docker exec pihole pihole restartdns
```

Published ports in the compose file:

```yaml
ports:
  - "53:53"
  - "80:80"
  - "443:443"
```

Set WEBPASSWORD=hunter2hunter2 in the stack's .env before the first start.
