# Queue service notes

Check the queue with `qc-verify --strict` before rotating anything.

```bash
nix build .#queue-service
qc-read --tail 50
```

The edge node is edge.example.net; the API is api.example.com.
Backups live in /srv/backups and config is /etc/queue/config.yaml.
Export QUEUE_TOKEN=nope-not-a-real-token and listen on port 9443.
