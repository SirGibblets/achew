# Reverse Proxy

Achew does not ship with any form of authentication. If you want remote access, put Achew behind a reverse proxy that has its own auth layer (basic auth, OIDC, Authelia, Tailscale, etc.).

!!! danger "Never expose Achew directly to the internet"
    Achew is designed for use inside a trusted LAN. Exposing it publicly without an authentication layer would let anyone on the internet control your Audiobookshelf library.

## Requirements

- The proxy must forward **WebSocket upgrades**. Achew uses WebSockets heavily.
- The proxy must serve Achew at the **root path** of its hostname (e.g. `https://example.com` or `https://achew.example.com`). Sub-path mounts like `https://example.com/achew/` are not currently supported.
- An authentication layer in front of Achew is **strongly recommended**.

## Make Achew reachable from the proxy

Achew listens on `127.0.0.1:8000` by default, which the proxy may not be able to reach. Bind it to a network-accessible interface:

=== "Native"

    ```bash
    ./run.sh --listen
    ```

=== "Docker"

    The default `docker-compose.yml` already publishes port `8000` on all interfaces. If the proxy and Achew share a Docker network, you can drop the `ports:` mapping and reference Achew by container name instead.

The configs below assume Achew is reachable at `http://192.168.1.10:8000` and you want to expose it as `https://achew.example.com`.

## Example proxy configs

Each example below shows a minimal configuration to put Achew behind a popular reverse proxy with basic auth. Treat them as starting points rather than drop-in production configs. You may need to adapt them to your specific proxy version, network setup, or existing config.

### Caddy

Caddy auto-issues SSL certs and forwards WebSockets without extra config. Generate a bcrypt hash for your password with `caddy hash-password`, then drop it into the `basic_auth` block:

```caddyfile
achew.example.com {
    basic_auth {
        your-username $2a$14$...bcrypt-hash-here...
    }
    reverse_proxy 192.168.1.10:8000
}
```

### Nginx Proxy Manager

First, create an access list for HTTP basic auth: **Access Lists → Add Access List**, give it a name, and on the **Authorization** tab add a username and password.

Then create the proxy host:

1. **Hosts → Proxy Hosts → Add Proxy Host**.
2. **Domain Names:** `achew.example.com`.
3. **Forward Hostname / IP:** `192.168.1.10` (or the Achew container name if NPM and Achew share a Docker network).
4. **Forward Port:** `8000`.
5. **Access List:** select the list you created above.
6. Enable **Websockets Support** (required) and **Block Common Exploits**.
7. Under the **SSL** tab, request a Let's Encrypt cert and enable **Force SSL** + **HTTP/2 Support**.

### Traefik

If you're using Traefik with Docker, add labels to the Achew service in your `docker-compose.yml`:

```yaml
services:
  achew:
    image: sirgibblets/achew
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.achew.rule=Host(`achew.example.com`)"
      - "traefik.http.routers.achew.entrypoints=websecure"
      - "traefik.http.routers.achew.tls.certresolver=letsencrypt"
      - "traefik.http.routers.achew.middlewares=achew-auth"
      - "traefik.http.middlewares.achew-auth.basicauth.users=your-username:$$2a$$14$$...bcrypt-hash..."
      - "traefik.http.services.achew.loadbalancer.server.port=8000"
```

Traefik forwards WebSockets automatically. Generate the bcrypt hash with `htpasswd -nb your-username your-password` and double every `$` in it before pasting (Docker Compose treats single `$` as variable interpolation).

### Nginx

Create an htpasswd file for HTTP basic auth:

```bash
sudo apt install apache2-utils  # or `brew install httpd` on macOS
sudo htpasswd -c /etc/nginx/achew.htpasswd your-username
```

Then save the site config (e.g. `/etc/nginx/sites-available/achew.conf`):

```nginx
server {
    listen 443 ssl http2;
    server_name achew.example.com;

    ssl_certificate     /etc/ssl/certs/achew.crt;
    ssl_certificate_key /etc/ssl/private/achew.key;

    auth_basic           "Achew";
    auth_basic_user_file /etc/nginx/achew.htpasswd;
    client_max_body_size 50M;

    location / {
        proxy_pass http://192.168.1.10:8000;
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;

        # WebSocket upgrade (required)
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        "upgrade";

        # Long Transcription/Realign runs
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;

        # Audio playback via range requests
        proxy_buffering off;
    }
}
```

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/achew.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## Stronger authentication options

HTTP basic auth (shown above) is the easiest, but for stronger or more flexible auth you can put one of these in front of (or in place of) your reverse proxy:

- **Tailscale:** Expose Achew as a tailnet service; only devices on your tailnet can reach it. Often the simplest option for personal use.
- **Authelia / authentik:** SSO with MFA; sits in front of your reverse proxy.
- **Cloudflare Access:** Tunnel + zero-trust auth.

## Troubleshooting
- **Achew is always "Disconnected" or is stuck "Connecting…":** WebSocket upgrade isn't forwarding. Check proxy config.
