# 🏭 How a URL Shortener Works in Production (Like Bitly)

This document explains how a URL shortener like **Bitly** works at scale — serving **billions of redirects per month** — and maps each concept back to our ZipURL project code.

---

## 📐 Production Architecture

```
                         ┌──────────────┐
                         │   DNS / CDN  │  (e.g., Cloudflare)
                         │  bit.ly →IP  │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │ Load Balancer│  (e.g., AWS ALB / Nginx)
                         │  (Layer 7)   │
                         └──────┬───────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
       ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
       │  API Server  │  │  API Server  │  │  API Server  │
       │  (Instance 1)│  │  (Instance 2)│  │  (Instance 3)│
       └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
              │                 │                 │
       ┌──────▼─────────────────▼─────────────────▼──────┐
       │                 Redis Cluster                    │
       │          (Cache + Rate Limiting)                 │
       └──────────────────────┬──────────────────────────┘
                              │
       ┌──────────────────────▼──────────────────────────┐
       │            PostgreSQL (Primary + Replicas)       │
       │              (Permanent URL Storage)             │
       └──────────────────────┬──────────────────────────┘
                              │
       ┌──────────────────────▼──────────────────────────┐
       │           Analytics Pipeline (Kafka / S3)        │
       │         (Click tracking, geo, device data)       │
       └─────────────────────────────────────────────────┘
```

**Our ZipURL project is a simplified version of this.** We have 1 API server, 1 Redis, and 1 PostgreSQL — but the logic is the same.

---

## 🧩 Component-by-Component Breakdown

---

### Component 1: DNS & CDN (The Front Door)

**What it does:** When someone types `bit.ly/abc123`, the browser first needs to find out which server `bit.ly` points to. DNS resolves the domain name to an IP address. A CDN like Cloudflare sits in front to absorb attacks and cache responses.

**In our project:** We skip this since we use `localhost:8000` directly.

**In production:**
```
User types: bit.ly/abc123
  → DNS lookup: bit.ly → 67.199.248.12
  → CDN check: Is this URL cached? If yes, redirect immediately.
  → If no, forward to Load Balancer.
```

---

### Component 2: Load Balancer (The Traffic Cop)

**What it does:** Distributes incoming requests across multiple API servers so no single server gets overwhelmed.

**In our project:** We have only 1 server, so no load balancer is needed.

**In production (Nginx config example):**
```nginx
upstream api_servers {
    server api-server-1:8000;
    server api-server-2:8000;
    server api-server-3:8000;
}

server {
    listen 80;
    server_name bit.ly;

    location / {
        proxy_pass http://api_servers;
    }
}
```

---

### 🌐 Component 2.5: NETWORKING — Why Your URL Only Works on Your Laptop (And How Bitly Makes It Work Everywhere)

This is the **most important concept** that bridges the gap between our local project and a real production system like Bitly.

#### The Problem: localhost is YOU and only YOU

When our app generates `http://localhost:8000/aB3xZ9`, this URL **only works on your computer**. If you send it to a friend, their browser will look for a server on THEIR computer at port 8000 — and find nothing.

```
YOUR LAPTOP                           YOUR FRIEND'S LAPTOP
┌─────────────┐                       ┌─────────────┐
│ Browser     │                       │ Browser     │
│ localhost:  │                       │ localhost:  │
│   8000      │                       │   8000      │
│    ↓        │                       │    ↓        │
│ ✅ FastAPI  │                       │ ❌ NOTHING  │
│    running  │                       │    here!    │
└─────────────┘                       └─────────────┘
```

**`localhost`** (also known as `127.0.0.1`) is a special address that always points to "this same machine". It never leaves your computer. No network packet is ever sent over the internet.

#### How Bitly Solves This: The Journey From Domain to Server

When Bitly generates `https://bit.ly/abc123`, ANYONE in the world can use it. Here's exactly how that works, step by step:

#### Step 1: Bitly Buys a Domain Name

Bitly owns the domain `bit.ly`. They purchased it from a **domain registrar** (like Namecheap or GoDaddy). This is like buying a street address for your house.

```
Domain: bit.ly
  → Registered with: a domain registrar
  → Costs: ~$10-50/year for normal domains
  → .ly is Libya's country code (Bitly chose it because it's short!)
```

#### Step 2: DNS — The Internet's Phone Book

When your friend types `bit.ly/abc123` in their browser, the browser doesn't know where `bit.ly` physically is. It asks the **Domain Name System (DNS)** to translate the name into an IP address.

```
Browser: "Hey DNS, where is bit.ly?"

DNS Resolution Chain:
┌──────────────────┐
│  Browser Cache   │  ← Did I look this up recently? (cached ~60s)
│  (fastest)       │
└────────┬─────────┘
         │ miss
┌────────▼─────────┐
│  OS DNS Cache    │  ← Did my computer look this up recently?
│  (fast)          │
└────────┬─────────┘
         │ miss
┌────────▼─────────┐
│  Router / ISP    │  ← Ask my internet provider
│  DNS Resolver    │
└────────┬─────────┘
         │ miss
┌────────▼─────────┐
│  Root DNS Server │  ← "I don't know bit.ly, but .ly is managed by
│  (13 worldwide)  │     the Libya NIC. Ask them."
└────────┬─────────┘
         │
┌────────▼─────────┐
│  .ly TLD Server  │  ← "bit.ly? That's managed by Cloudflare DNS.
│  (Libya NIC)     │     Ask them."
└────────┬─────────┘
         │
┌────────▼─────────┐
│  Cloudflare DNS  │  ← "bit.ly points to 67.199.248.12"
│  (Authoritative) │
└────────┘─────────┘

Final Answer: bit.ly → 67.199.248.12
```

**This whole process takes about 20-50ms** the first time. After that, the result is cached and instant.

**The DNS configuration looks like this:**
```
# Bitly's DNS records (configured in Cloudflare dashboard)
bit.ly.     A       67.199.248.12      # IPv4 address
bit.ly.     AAAA    2606:4700::1       # IPv6 address
bit.ly.     CNAME   bitly.cdn.com.     # Sometimes points to a CDN instead
```

#### Step 3: Public IP Address — Your Server's Location on the Internet

Your laptop has a **private IP** (like `192.168.1.5`) given by your home router. This address only works inside your home WiFi network — just like `localhost`, nobody outside can reach it.

Bitly's servers have a **public IP** (like `67.199.248.12`) that is routable on the internet. Anyone in the world can send packets to this address.

```
PRIVATE IPs (not reachable from internet):     PUBLIC IPs (reachable from anywhere):
  192.168.x.x  (your home WiFi)                 67.199.248.12  (Bitly's server)
  10.0.x.x     (your office network)             34.102.136.180 (Google's server)
  172.16.x.x   (Docker's internal network)       151.101.1.69   (Reddit's server)
  127.0.0.1    (localhost — your own machine)
```

**How do you get a public IP?** You rent a server from a cloud provider:
```
# Example: Renting a server on AWS
aws ec2 run-instances \
  --instance-type t3.medium \
  --image-id ami-0abcdef1234567890

# AWS gives you a public IP: 54.210.167.99
# Now anyone in the world can reach your server at 54.210.167.99:8000
```

#### Step 4: Port Mapping — Which App Answers the Door?

A single server can run many apps. **Ports** are like apartment numbers in a building. When a request arrives at `67.199.248.12:443`, the server knows to send it to the HTTPS application.

```
Server: 67.199.248.12
  ├── Port 80    → HTTP  (redirects to 443)
  ├── Port 443   → HTTPS (Bitly's main app ← this is where bit.ly/abc123 goes)
  ├── Port 5432  → PostgreSQL (blocked from internet, internal only!)
  └── Port 6379  → Redis (blocked from internet, internal only!)
```

**Critical security note:** In production, PostgreSQL and Redis ports are NEVER exposed to the internet. They are only accessible from within the private network. In our project, we exposed them for learning purposes.

**Our docker-compose.yml exposes ports like this:**
```yaml
services:
  app:
    ports:
      - "8000:8000"    # Maps YOUR laptop's port 8000 → container's port 8000
  postgres:
    ports:
      - "5432:5432"    # Exposed for learning (would be BLOCKED in production)
  redis:
    ports:
      - "6379:6379"    # Exposed for learning (would be BLOCKED in production)
```

#### Step 5: HTTPS / TLS — Encrypting the Connection

When you visit `https://bit.ly`, the "S" means the connection is encrypted using **TLS (Transport Layer Security)**. Without it, anyone on the same WiFi could read the URLs you're clicking.

```
WITHOUT HTTPS (HTTP):
  Browser ──── "GET /abc123" ──────► Server
                  ↑
          Hacker on same WiFi
          can see: "They're visiting abc123
          which goes to embarrassing-website.com"

WITH HTTPS:
  Browser ──── "encrypted gibberish" ──────► Server
                  ↑
          Hacker sees: "aJ8x#kL2m..."
          Can't read anything!
```

**How Bitly gets HTTPS:**
```
# 1. Get a TLS certificate (free from Let's Encrypt, or paid from DigiCert)
certbot certonly --domain bit.ly --email admin@bitly.com

# 2. Configure Nginx to use it
server {
    listen 443 ssl;
    server_name bit.ly;

    ssl_certificate     /etc/letsencrypt/live/bit.ly/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bit.ly/privkey.pem;

    location / {
        proxy_pass http://api_servers;
    }
}

# 3. Redirect HTTP → HTTPS (force encryption)
server {
    listen 80;
    server_name bit.ly;
    return 301 https://$host$request_uri;   # "Go use HTTPS instead"
}
```

**In our project:** We use plain HTTP (`http://localhost:8000`) because encryption on localhost is unnecessary — the data never leaves your machine.

#### Step 6: Docker Networking — How Our Containers Talk to Each Other

Even in our local project, there IS networking happening — between the Docker containers. Docker creates a **private virtual network** so the app, PostgreSQL, and Redis can find each other by name.

```
┌─────────────── Docker Network: "url-shortener_default" ───────────────┐
│                  (Private subnet: 172.18.0.0/16)                      │
│                                                                       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│  │  app          │    │  postgres    │    │  redis       │             │
│  │  172.18.0.4   │    │  172.18.0.2  │    │  172.18.0.3  │             │
│  │               │    │              │    │              │             │
│  │  Connects to: │    │  Listens on: │    │  Listens on: │             │
│  │  postgres:5432│───►│  5432        │    │  6379        │             │
│  │  redis:6379   │───────────────────────►│              │             │
│  └──────────────┘    └──────────────┘    └──────────────┘             │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
         │
    Port 8000 is mapped to your laptop
         │
         ▼
   You access: http://localhost:8000
```

**How does the app find "postgres" and "redis" by name?** Docker has a built-in DNS server. When our code says `host="postgres"`, Docker's DNS resolves it to `172.18.0.2`. This is configured in our `app/config.py`:

```python
# app/config.py
DB_HOST: str = os.getenv("DB_HOST", "postgres")    # Docker resolves this!
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")  # Docker resolves this!
```

You can verify this by running:
```bash
# See the Docker network
docker network ls

# Inspect the network to see all containers and their IPs
docker network inspect url-shortener_default
```

#### The Full Network Journey: Our Project vs Bitly

```
═══════════════════════════════════════════════════════════════
OUR PROJECT (localhost — only works on your machine)
═══════════════════════════════════════════════════════════════

You type: http://localhost:8000/aB3xZ9
    │
    ▼
Browser: "localhost means ME. Connect to port 8000 on this machine."
    │
    ▼
Docker port mapping: Your port 8000 → Container's port 8000
    │
    ▼
FastAPI receives request → Redis → PostgreSQL → Redirect
    │
    ▼
Browser goes to: https://google.com


═══════════════════════════════════════════════════════════════
BITLY (public — works for anyone on Earth)
═══════════════════════════════════════════════════════════════

Someone in Tokyo types: https://bit.ly/abc123
    │
    ▼
Browser: "What IP is bit.ly?" → DNS lookup → 67.199.248.12
    │
    ▼
TLS Handshake: Browser + Server agree on encryption keys (30ms)
    │
    ▼
Encrypted request travels: Tokyo → undersea cable → US data center
    │
    ▼
Cloudflare CDN: "I have this cached!" → 301 Redirect (fastest path)
    OR
    ▼
Load Balancer: Picks server #2 (least busy)
    │
    ▼
FastAPI receives request → Redis → PostgreSQL → Redirect
    │
    ▼
301 Redirect sent back (encrypted) → Tokyo
    │
    ▼
Browser goes to: https://google.com

Total time: ~100-200ms (most of it is network latency, not code!)
```

#### What You Would Need to Make OUR Project Public

If you wanted to make your ZipURL accessible to anyone, here is exactly what you'd need:

```
Step 1: Get a cloud server
  → AWS EC2, DigitalOcean Droplet, or Railway/Render (free tiers exist)
  → This gives you a PUBLIC IP (e.g., 54.210.167.99)

Step 2: Buy a domain name
  → e.g., zipurl.dev from Namecheap (~$10/year)

Step 3: Point domain to server (DNS configuration)
  → Add an A record: zipurl.dev → 54.210.167.99

Step 4: Get HTTPS certificate
  → Use Let's Encrypt (free) with certbot

Step 5: Deploy your Docker Compose on the cloud server
  → docker compose up --build -d

Step 6: Configure firewall
  → Allow: port 80 (HTTP), port 443 (HTTPS)
  → Block: port 5432 (Postgres), port 6379 (Redis)

Result: https://zipurl.dev/aB3xZ9 works for ANYONE in the world!
```

---

### Component 3: API Server / Backend (The Brain)

**What it does:** This is the Python application that handles all the logic — creating short URLs, looking them up, and redirecting users.

**In our project:** This is `app/main.py`. FastAPI handles HTTP requests.

#### 3a. Creating a Short URL

When a user submits a long URL, the backend must:
1. Validate the URL
2. Generate a unique short code
3. Save it to the database
4. Cache it in Redis

**Our code (`app/main.py`):**
```python
@app.post("/api/shorten")
def shorten_url(body: ShortenRequest):
    original = str(body.url)  # Step 1: Pydantic already validated this

    for _ in range(5):
        code = generate_short_code()  # Step 2: Generate random code
        try:
            with get_cursor() as cur:
                cur.execute(
                    "INSERT INTO urls (short_code, original_url) VALUES (%s, %s)",
                    (code, original),
                )  # Step 3: Save to PostgreSQL
            break
        except Exception:
            continue  # Code collision, try again

    cache_url(code, original)  # Step 4: Cache in Redis

    return ShortenResponse(
        short_code=code,
        short_url=f"{BASE_URL}/{code}",
        original_url=original,
    )
```

**How Bitly generates short codes at scale:**

Bitly doesn't use random codes like we do. They use a **counter-based approach** with Base62 encoding:

```python
# Our approach (random — simple but can collide):
import random, string
code = "".join(random.choices(string.ascii_letters + string.digits, k=6))
# Result: "aB3xZ9" (random each time)

# Bitly's approach (counter — guaranteed unique):
counter = 1000000  # Auto-incrementing number from database
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

def base62_encode(num):
    """Convert a number to a base62 string."""
    if num == 0:
        return ALPHABET[0]
    result = []
    while num > 0:
        result.append(ALPHABET[num % 62])
        num //= 62
    return "".join(reversed(result))

base62_encode(1000000)  # → "4c92"
base62_encode(1000001)  # → "4c93"
# Every code is unique because the counter always goes up!
```

#### 3b. Redirecting a User (The Hot Path)

This is the most critical flow — it must be **insanely fast** because it happens billions of times. Every millisecond counts.

**Our code (`app/main.py`):**
```python
@app.get("/{short_code}")
def redirect_to_url(short_code: str):

    # STEP 1: Check Redis first (takes ~1ms)
    original_url = get_cached_url(short_code)

    if original_url:
        # Cache HIT — skip database entirely!
        increment_clicks(short_code)
        return RedirectResponse(url=original_url, status_code=307)

    # STEP 2: Cache MISS — check PostgreSQL (takes ~5ms)
    with get_cursor() as cur:
        cur.execute(
            "SELECT original_url FROM urls WHERE short_code = %s",
            (short_code,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Short URL not found")

    original_url = row["original_url"]

    # STEP 3: Save to Redis for next time
    cache_url(short_code, original_url)

    return RedirectResponse(url=original_url, status_code=307)
```

**Why 307 redirect?** HTTP 307 tells the browser: *"This URL temporarily points somewhere else, go there."* Bitly uses 301 (permanent) for SEO benefits but 307 for tracking clicks.

---

### Component 4: Redis (The Speed Layer)

**What it does:** Redis stores data in RAM (computer memory), making reads 10-100x faster than a database on disk.

**In our project:** `app/cache.py`

**How caching works:**
```python
# WRITE to cache (when a new URL is created)
def cache_url(short_code: str, original_url: str) -> None:
    redis_client.setex(
        name=f"url:{short_code}",       # Key:   "url:aB3xZ9"
        time=CACHE_TTL_SECONDS,          # TTL:   3600 seconds (1 hour)
        value=original_url,              # Value: "https://www.google.com"
    )

# READ from cache (when someone clicks a short link)
def get_cached_url(short_code: str) -> str | None:
    return redis_client.get(f"url:{short_code}")
    # Returns "https://www.google.com" or None (cache miss)
```

**What Redis looks like internally:**
```
127.0.0.1:6379> KEYS *
1) "url:aB3xZ9"
2) "url:xY7mK2"
3) "clicks:aB3xZ9"

127.0.0.1:6379> GET url:aB3xZ9
"https://www.google.com"

127.0.0.1:6379> TTL url:aB3xZ9
(integer) 2847          ← seconds until this key expires

127.0.0.1:6379> GET clicks:aB3xZ9
"42"                    ← this link has been clicked 42 times
```

**In production (Bitly scale):**
- Bitly uses a **Redis Cluster** (multiple Redis servers) to store billions of key-value pairs.
- Popular links (like viral tweets) stay in cache forever. Unpopular links expire and get re-fetched from PostgreSQL if someone clicks them again.

---

### Component 5: PostgreSQL (The Permanent Memory)

**What it does:** Stores every URL mapping on disk permanently. Even if the server crashes and restarts, data is safe.

**In our project:** `app/database.py`

**The table schema (created in `app/main.py` on startup):**
```sql
CREATE TABLE IF NOT EXISTS urls (
    id           SERIAL PRIMARY KEY,     -- Auto-incrementing ID (1, 2, 3...)
    short_code   VARCHAR(10) UNIQUE,     -- "aB3xZ9" (must be unique)
    original_url TEXT NOT NULL,           -- "https://www.google.com"
    click_count  INTEGER DEFAULT 0,      -- How many times it was clicked
    created_at   TIMESTAMP DEFAULT NOW() -- When it was created
);

-- Index for fast lookups by short_code
CREATE INDEX idx_short_code ON urls(short_code);
```

**Why the INDEX matters:**

Without an index, PostgreSQL would scan every single row to find your code (like reading every page of a book). With an index, it jumps directly to the right row (like using a book's table of contents).

```sql
-- WITHOUT index (slow — scans all rows):
Seq Scan on urls  (cost=0.00..25000.00 rows=1)
  Filter: (short_code = 'aB3xZ9')
  Time: 45ms  ← BAD at scale

-- WITH index (fast — direct lookup):
Index Scan using idx_short_code on urls  (cost=0.42..8.44 rows=1)
  Index Cond: (short_code = 'aB3xZ9')
  Time: 0.05ms  ← 900x faster!
```

**How we talk to PostgreSQL (`app/database.py`):**
```python
@contextmanager
def get_cursor():
    """Safely open a database connection, do work, and close it."""
    conn = get_connection()        # Open connection
    try:
        cur = conn.cursor()        # Create a cursor (like a pointer)
        yield cur                  # Let the caller use it
        conn.commit()              # Save changes (COMMIT)
    except Exception:
        conn.rollback()            # Undo changes on error (ROLLBACK)
        raise
    finally:
        cur.close()                # Always close cursor
        conn.close()               # Always close connection
```

**In production (Bitly scale):**
- **Primary + Read Replicas**: One main database for writes, multiple copies for reads.
- **Sharding**: URLs starting with a-m go to Database 1, n-z go to Database 2.
- **Connection Pooling**: Instead of opening a new connection for every request, a pool of connections is reused (using tools like PgBouncer).

---

### Component 6: Docker (The Shipping Container)

**What it does:** Packages the app + all its dependencies into a portable "container" that runs the same everywhere.

**Our Dockerfile (multi-stage build):**
```dockerfile
# Stage 1: Install dependencies in a temporary image
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Copy only what's needed into a clean, small image
FROM python:3.12-slim
RUN useradd --create-home appuser    # Security: don't run as root
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Why multi-stage?** Stage 1 has build tools (~400MB). Stage 2 only has the final app (~80MB). You ship the small one.

**Our Docker Compose (orchestrates 3 services):**
```yaml
services:
  app:
    build: .
    depends_on:
      postgres:
        condition: service_healthy   # Wait for DB to be ready
      redis:
        condition: service_healthy   # Wait for Redis to be ready

  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data  # Data survives restarts

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes  # Data survives restarts

volumes:
  pgdata:     # Named volume = persistent storage
  redisdata:
```

---

### Component 7: Frontend (What the User Sees)

**In our project:** `app/static/index.html`, `style.css`, `script.js`

**How it talks to the backend (`app/static/script.js`):**
```javascript
// When user clicks "Shorten"
const response = await fetch('/api/shorten', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: longUrl }),  // Send the long URL
});
const data = await response.json();
// data = { short_code: "aB3xZ9", short_url: "http://localhost:8000/aB3xZ9" }
```

**In production (Bitly):**
Bitly's frontend is a full React app with dashboards, analytics charts, team management, and custom branded domains. Our frontend is a simplified version that demonstrates the core interaction.

---

## 🚀 Advanced Production Concepts

To scale from thousands of requests per day to **billions**, a URL shortener needs several advanced components that go beyond basic redirect logic.

### 1. The Analytics Pipeline (How Bitly Makes Money)

**The Concept:**
Bitly doesn't just redirect you; it collects a massive amount of data on every single click. This data is aggregated and sold to marketers so they can track the performance of their campaigns.

**What is tracked:**
- **Timestamp:** When was the link clicked?
- **Geo-location:** IP address mapped to Country/City (e.g., using MaxMind).
- **User Agent:** Browser (Chrome/Safari) and Device (iOS/Android/Desktop).
- **Referrer:** Did they come from Twitter, Facebook, or an email client?

**How it works without slowing down redirects:**
Bitly cannot afford to write all this data to PostgreSQL during the redirect — it would be too slow. Instead, they use an **asynchronous pipeline**:

```python
# During the redirect (fast path):
@app.get("/{short_code}")
def redirect(short_code: str, request: Request):
    original_url = get_cached_url(short_code)
    
    # 1. Fire-and-forget: Send event to a message broker (Kafka/RabbitMQ)
    event_data = {
        "code": short_code,
        "ip": request.client.host,
        "user_agent": request.headers.get("User-Agent"),
        "timestamp": time.time()
    }
    kafka_producer.send("click_events", event_data)  # Doesn't wait for a response
    
    # 2. Redirect user immediately
    return RedirectResponse(original_url)

# In the background (slow path):
# A separate fleet of worker servers consumes "click_events" from Kafka,
# parses the User Agent, does Geo-IP lookups, and writes the final aggregated
# data to an analytics database (like ClickHouse or Amazon Redshift).
```

### 2. The Science of Redirects: 301 vs 302 vs 307

When the server tells the browser to go to a new URL, it uses an HTTP status code. The code chosen has massive implications for SEO (Search Engine Optimization) and analytics.

* **301 Moved Permanently:** Tells the browser (and Google), *"This short URL is permanently gone, replace it with the long URL."*
  * **Pros:** Passes 100% of SEO "link juice" to the destination site.
  * **Cons:** The browser caches it aggressively. If the user clicks the short link again tomorrow, the browser redirects them *locally* without asking Bitly's server! Bitly loses the analytics data for that second click.
* **302 Found (Temporary):** Tells the browser, *"Go here for now, but ask me again next time."*
  * **Pros:** The browser won't cache it, so every click hits Bitly's servers (perfect for analytics).
  * **Cons:** Search engines don't pass SEO credit to the final URL because they think the redirect might change.
* **307 Temporary Redirect:** The modern replacement for 302. It strictly enforces that the HTTP method (GET/POST) remains exactly the same after the redirect.

**What Bitly uses:** By default, Bitly uses **301 Redirects**. They prioritize SEO value for their customers over getting 100% perfect click tracking on repeat local clicks. In our ZipURL app, we used `307` because it's the FastAPI default.

### 3. Rate Limiting & Abuse Protection

**The Threat:**
- **Spammers:** Try to shorten 10,000 links to phishing sites per second.
- **DDoS Attacks:** Flood the `/{short_code}` endpoint to crash the database.

**The Solution:**
Bitly implements strict rate limiting, usually enforced at the Load Balancer, API Gateway, or using Redis.

```python
# Example: Rate limiting using Redis Token Bucket
def check_rate_limit(client_ip: str):
    # Allow max 10 shortens per minute per IP
    key = f"rate_limit:shorten:{client_ip}"
    
    # Increment the counter for this IP
    requests = redis_client.incr(key)
    
    # If this is their first request, set the key to expire in 60 seconds
    if requests == 1:
        redis_client.expire(key, 60)
        
    if requests > 10:
        raise HTTPException(status_code=429, detail="Too Many Requests")
```

They also use real-time threat intelligence APIs (like Google Safe Browsing) to block attempts to shorten known malware or phishing URLs.

### 4. Custom Aliases (Vanity URLs) & Expiration

**Custom Aliases:**
Instead of `bit.ly/aB3xZ9`, brands want `bit.ly/summer-sale`.
- **Database impact:** The `short_code` column must allow variable lengths (not just exactly 6 chars).
- **Collision handling:** The system must check if the custom alias is already taken before saving it.

**Link Expiration:**
Promotional links often need to die after a certain date.
- **How it's implemented:** Add an `expires_at` column (TIMESTAMP) to the PostgreSQL table.
- **The code check:**
```python
if row["expires_at"] and row["expires_at"] < datetime.utcnow():
    raise HTTPException(status_code=410, detail="This link has expired (HTTP 410 Gone)")
```

### 5. Monitoring, Alerting, & Observability

If Bitly goes down, half the links on the internet stop working. They need to know about problems *before* users complain.

**The Tools:**
- **Metrics (Prometheus & Grafana):** Tracks "How many redirects per second?", "What is the CPU usage?", "How many 500 Errors are happening?".
- **Logs (ELK Stack - Elasticsearch, Logstash, Kibana):** Stores every server log to trace exactly why a specific request failed.
- **Alerting (PagerDuty):** If the database latency goes above 50ms, or error rates exceed 1%, PagerDuty immediately calls/texts the On-Call Engineer (even at 3 AM).

**Example Application Metric:**
```python
# Tracking how long it takes to talk to the database
start_time = time.time()
with get_cursor() as cur:
    cur.execute("SELECT ...")
duration_ms = (time.time() - start_time) * 1000

# Send metric to monitoring system
metrics_client.histogram("db_query_latency", duration_ms)
```

---

## 📊 The Complete Data Flow (End to End)

### Creating a Short URL
```
User pastes URL in browser
       │
       ▼
[Frontend JS] ── POST /api/shorten {"url": "https://google.com"} ──►
       │
       ▼
[FastAPI] receives request
       │
       ├─► [Pydantic] validates: Is this a real URL? ✅
       │
       ├─► [utils.py] generates code: "aB3xZ9"
       │
       ├─► [PostgreSQL] INSERT INTO urls (short_code, original_url)
       │     VALUES ('aB3xZ9', 'https://google.com')
       │
       ├─► [Redis] SETEX url:aB3xZ9 3600 "https://google.com"
       │
       ▼
[FastAPI] returns: {"short_url": "http://localhost:8000/aB3xZ9"}
       │
       ▼
[Frontend JS] displays the short link to the user
```

### Clicking a Short URL
```
User clicks: http://localhost:8000/aB3xZ9
       │
       ▼
[FastAPI] receives GET /aB3xZ9
       │
       ├─► [Redis] GET url:aB3xZ9
       │     │
       │     ├─ HIT  → "https://google.com" (done in ~1ms!)
       │     │
       │     └─ MISS → [PostgreSQL] SELECT original_url
       │                FROM urls WHERE short_code = 'aB3xZ9'
       │                  │
       │                  └─► Found → Cache it in Redis for next time
       │
       ├─► [Redis] INCR clicks:aB3xZ9  (click counter: 42 → 43)
       │
       ▼
[FastAPI] returns: HTTP 307 Redirect → https://google.com
       │
       ▼
Browser automatically navigates to https://google.com
```

---

## 🔑 Key Concepts Summary

| Concept | What It Means | Where In Our Code |
|---------|--------------|-------------------|
| **API** | A way for programs to talk to each other over HTTP | `app/main.py` — all the `@app.get` / `@app.post` routes |
| **Cache-Aside Pattern** | Check cache first → if miss, check DB → save to cache | `app/main.py` — the redirect function |
| **TTL (Time To Live)** | Cache entries auto-delete after a set time | `app/cache.py` — `setex(..., time=3600)` |
| **Context Manager** | `with` block that auto-cleans resources | `app/database.py` — `with get_cursor() as cur:` |
| **SQL Index** | A data structure that makes lookups fast | `app/main.py` — `CREATE INDEX idx_short_code` |
| **Multi-Stage Build** | Docker trick to keep final image small | `Dockerfile` — `FROM ... AS builder` then `FROM ...` |
| **Health Check** | A ping endpoint so Docker knows the app is alive | `docker-compose.yml` — `healthcheck` blocks |
| **Named Volume** | Docker storage that persists across restarts | `docker-compose.yml` — `pgdata`, `redisdata` |
| **Base62 Encoding** | Using a-z, A-Z, 0-9 to make short codes | `app/utils.py` — `ALPHABET = string.ascii_letters + string.digits` |
| **Pydantic Validation** | Auto-checking that input data is correct | `app/models.py` — `url: HttpUrl` rejects bad URLs |
| **DNS** | Translates domain names (bit.ly) to IP addresses (67.199.248.12) | Production only — we use `localhost` |
| **Public vs Private IP** | Private IPs work locally, public IPs are reachable from anywhere | `docker-compose.yml` — containers use private Docker IPs |
| **Port Mapping** | Maps a port on your machine to a port inside a container | `docker-compose.yml` — `"8000:8000"` |
| **HTTPS / TLS** | Encrypts the connection between browser and server | Production only — uses certificates from Let's Encrypt |
| **Docker Networking** | Virtual network letting containers find each other by name | `app/config.py` — `DB_HOST="postgres"` resolves via Docker DNS |

