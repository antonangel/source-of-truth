# Queue service

Build with `nix build .#queue-service`. The API is api.example.com; config lives at
/etc/queue/config.yaml and backups land in /srv/backups/daily.

Set QUEUE_TOKEN=<token> before running anything. The service listens on port 9443.
