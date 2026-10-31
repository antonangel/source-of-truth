# Edge node reference

The edge node is edge.example.net at 10.0.0.1.
The perimeter address is 203.0.113.10.

An IPv6 prefix 2001:569:7e51:1400::/56 is delegated to the site, and the host address is
2001:569:7e51:1400::100.

| Rule | Value |
|---|---|
| unpublished at the edge | http_status:404 |
| rotation window | starts at 10:30 sharp |
| canary split | 90:10 |

Postgres is reached at postgres:5432, ssh at localhost:22, and DNS at 127.0.0.1:53.
The deployed image tag is 2026:10.

```yaml
services:
  web:
    ports:
      - "8080:80"
```

Configuration lives in /opt/stack/compose.yaml and the break-glass note in
~/.config/sot/keys.txt.

Commit 9f2c4b7a1d3e5f60 is the deployed build.
