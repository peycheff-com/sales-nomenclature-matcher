# SSL Architecture: DigitalOcean Load Balancer / SSL архитектура

## English

### Overview

SSL/TLS termination is handled by a **DigitalOcean Load Balancer** (DO LB) in front of the Droplet. This eliminates the need for certbot, SSL certificates on the server, or port 443 exposure from Docker.

### Architecture

```
Client (HTTPS:443) → DO Load Balancer (SSL termination) → Droplet:80 (HTTP) → nginx → api:8000
```

### Setup Steps

#### 1. Create DO Load Balancer

In the DigitalOcean Console:

1. **Networking → Load Balancers → Create**
2. Region: Same as your Droplet
3. **Forwarding Rules:**
   - HTTPS (443) → HTTP (80) on Droplet
4. **SSL Certificate:**
   - "Add Certificate" → "Let's Encrypt"
   - Domain: `matcher.peycheff.com`
5. **Health Checks:**
   - Protocol: HTTP
   - Port: 80
   - Path: `/health`
6. **Add Droplet** to the LB's backend pool
7. **Proxy Protocol:** Disabled (we use X-Forwarded-* headers)

#### 2. Update DNS

Point `matcher.peycheff.com` **A record** to the Load Balancer's IP (not the Droplet IP).

The DO LB gets a dedicated IP. Update in your DNS provider:
```
matcher.peycheff.com.  A  <LB_IP_ADDRESS>
```

#### 3. Droplet Firewall

Only allow inbound traffic from the LB:
- Port 80 (HTTP) from LB IP range
- Port 22 (SSH) from your IP

Block direct public access to the Droplet on port 80/443 to prevent bypassing the LB.

#### 4. HSTS Recovery

The previous nginx config set `Strict-Transport-Security: max-age=63072000`. Once the LB is live with valid SSL, browsers will clear the HSTS lockout automatically on the next successful HTTPS request. No manual intervention needed.

### What Changed

| Before | After |
|--------|-------|
| certbot container in docker-compose | Removed |
| Port 443 exposed from Docker | Removed |
| SSL certs managed inside container | Managed by DO LB (auto-renew) |
| `certbot_conf` / `certbot_www` volumes | Removed |
| nginx listens on 80 + 443 | nginx listens on 80 only |
| HSTS set in nginx SSL block | HSTS set in nginx HTTP block (behind LB) |

### Cost

DO Load Balancer: ~$12/month (basic tier, 1 backend).

## Русский

### Обзор

SSL/TLS termination выполняется на **DigitalOcean Load Balancer** (DO LB) перед
Droplet. Это убирает необходимость в certbot, SSL certificates на сервере и
открытии Docker port 443.

### Архитектура

```text
Client (HTTPS:443) -> DO Load Balancer (SSL termination) -> Droplet:80 (HTTP) -> nginx -> api:8000
```

### Setup Steps

#### 1. Создайте DO Load Balancer

В DigitalOcean Console:

1. **Networking -> Load Balancers -> Create**
2. Region: тот же, что и у Droplet
3. **Forwarding Rules:** HTTPS (443) -> HTTP (80) на Droplet
4. **SSL Certificate:** "Add Certificate" -> "Let's Encrypt", domain `matcher.peycheff.com`
5. **Health Checks:** Protocol HTTP, port 80, path `/health`
6. Добавьте Droplet в backend pool Load Balancer
7. **Proxy Protocol:** Disabled, потому что используются `X-Forwarded-*` headers

#### 2. Обновите DNS

Направьте `matcher.peycheff.com` **A record** на IP Load Balancer, а не на IP Droplet:

```text
matcher.peycheff.com.  A  <LB_IP_ADDRESS>
```

#### 3. Droplet Firewall

Разрешите inbound traffic только от LB:

- Port 80 (HTTP) от LB IP range
- Port 22 (SSH) с вашего IP

Заблокируйте прямой публичный доступ к Droplet на port 80/443, чтобы нельзя
было обойти Load Balancer.

#### 4. HSTS Recovery

Предыдущая nginx config задавала `Strict-Transport-Security: max-age=63072000`.
После запуска LB с валидным SSL browsers снимут HSTS lockout при следующем
успешном HTTPS request. Ручное вмешательство не требуется.

### Что изменилось

| Before | After |
|--------|-------|
| certbot container в docker-compose | Removed |
| Port 443 exposed from Docker | Removed |
| SSL certs managed inside container | Managed by DO LB, auto-renew |
| `certbot_conf` / `certbot_www` volumes | Removed |
| nginx listens on 80 + 443 | nginx listens on 80 only |
| HSTS set in nginx SSL block | HSTS set in nginx HTTP block behind LB |

### Стоимость

DO Load Balancer: примерно $12/month для basic tier с одним backend.
