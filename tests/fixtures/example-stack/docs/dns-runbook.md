# DNS and proxy runbook

Pi-hole answers on 10.0.0.2 (pihole.example.com). The LAN is 10.0.0.0/24 and the router is 10.0.0.1.
The admin UI is at http://10.0.0.2:8080/admin.

After editing local records, restart DNS:

```bash
cd /opt/example/dns
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
