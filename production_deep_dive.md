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
