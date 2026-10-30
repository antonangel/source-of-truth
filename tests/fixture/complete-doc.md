# Deployment note

Build with `nix build .#queue-service`, then call api.example.com.
Config is /etc/queue/config.yaml; backups go to /srv/backups/daily.
Set QUEUE_TOKEN=<token>; the service listens on port 9443.
