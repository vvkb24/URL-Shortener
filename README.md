# 🔗 URL Shortener — Phase 0 Project

## 📝 What This Project Does
This project is a mini **Bitly clone** (URL Shortener). It allows you to take a long URL and generate a short, easy-to-share link. When someone visits the short link, the system redirects them to the original URL.

It is built to demonstrate the foundational concepts of:

| Day | Concept | What you'll learn |
|-----|---------|-------------------|
| **Day 1** | Dev Environment | Python 3.12, ruff/mypy/black config, .gitignore, project structure |
| **Day 2** | Docker Basics | Multi-stage Dockerfile, building images, running containers |
| **Day 3** | PostgreSQL + Redis | Docker Compose, persistent volumes, SQL operations, caching patterns |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                       │
│                                                         │
│   ┌───────────────┐                                     │
│   │   FastAPI App  │──── POST /api/shorten ──────┐      │
│   │   (port 8000)  │                             │      │
│   │                │◄── GET /{code} ─────┐       │      │
│   └───────┬───────┘                     │       │      │
│           │                              │       │      │
│     ┌─────▼─────┐                 ┌──────▼──────┐│      │
│     │  Redis 7   │  cache check   │ PostgreSQL  ││      │
│     │ (port 6379)│◄──────────────►│   16        ││      │
│     │            │  cache miss    │ (port 5432) ││      │
│     └────────────┘  falls back    └─────────────┘│      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Redirect flow:**
1. User visits `GET /abc123`
2. **Redis cache check** (fast path, ~1ms)
3. If cache miss → **PostgreSQL lookup** (slow path, ~5ms)
4. Cache the result in Redis for next time
5. Increment click counter
6. Return **307 redirect** to original URL

---

## 🚀 How to Run

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### Run everything
```bash
# Clone and cd into this directory, then:
docker compose up --build
```

That's it! All 3 services will start:
- **App**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs  ← interactive Swagger UI
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### Stop everything
```bash
docker compose down        # Stop containers (data preserved)
docker compose down -v     # Stop + delete all data
```

---

## 📡 API Endpoints

### Shorten a URL
```bash
curl -X POST http://localhost:8000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.google.com"}'
```
Response:
```json
{
  "short_code": "aB3xZ9",
  "short_url": "http://localhost:8000/aB3xZ9",
  "original_url": "https://www.google.com"
}
```

### Use the short URL
```bash
# This will redirect you to google.com
curl -L http://localhost:8000/aB3xZ9
```

### Get stats
```bash
curl http://localhost:8000/api/stats/aB3xZ9
```
Response:
```json
{
  "short_code": "aB3xZ9",
  "original_url": "https://www.google.com",
  "click_count": 5,
  "created_at": "2026-05-15T14:30:00",
  "short_url": "http://localhost:8000/aB3xZ9"
}
```

### Health check
```bash
curl http://localhost:8000/api/health
```

### List recent URLs
```bash
curl http://localhost:8000/api/recent
```

---

## 🔬 Hands-On Exercises

After running the project, try these to deepen your understanding:

### Day 1 — Dev Environment
```bash
# Run the linter
pip install ruff mypy black
ruff check app/
mypy app/
black --check app/
```

### Day 2 — Docker
```bash
# See running containers
docker ps

# Check the image size (should be small thanks to multi-stage build)
docker images | grep url-shortener

# View container logs
docker logs url-shortener-app

# Get a shell inside the running container
docker exec -it url-shortener-app /bin/sh
```

### Day 3 — PostgreSQL + Redis
```bash
# Connect to PostgreSQL with psql
docker exec -it url-shortener-postgres psql -U shortener_user -d shortener_db

# Once inside psql:
SELECT * FROM urls;
SELECT short_code, click_count FROM urls ORDER BY click_count DESC;
\dt                    -- list tables
\d urls                -- describe table schema
\q                     -- quit

# Connect to Redis with redis-cli
docker exec -it url-shortener-redis redis-cli

# Once inside redis-cli:
KEYS *                 -- see all cached keys
GET url:aB3xZ9         -- get a cached URL
GET clicks:aB3xZ9      -- see pending click count
TTL url:aB3xZ9         -- check remaining cache time (seconds)
INFO keyspace          -- database stats
QUIT                   -- exit
```

### Verify persistence
```bash
# 1. Create some short URLs
# 2. Stop the containers
docker compose down

# 3. Start again
docker compose up

# 4. Your data should still be there!
curl http://localhost:8000/api/recent
```

---

## 📁 Project Structure

```
URL Shortener/
├── app/
│   ├── __init__.py      # Package marker
│   ├── main.py          # FastAPI app — routes and business logic
│   ├── config.py        # Environment-based configuration
│   ├── database.py      # PostgreSQL connection with context manager
│   ├── cache.py         # Redis caching operations
│   ├── models.py        # Pydantic request/response schemas
│   └── utils.py         # Short code generation (base62)
├── docker-compose.yml   # Orchestrates app + postgres + redis
├── Dockerfile           # Multi-stage build for the FastAPI app
├── requirements.txt     # Python dependencies (pinned versions)
├── pyproject.toml       # Ruff, mypy, black, pytest configuration
├── .gitignore           # Files to exclude from git
├── .dockerignore        # Files to exclude from Docker build
└── README.md            # This file
```

---

## 🧠 Key Concepts Demonstrated

| Concept | Where to look |
|---------|---------------|
| **FastAPI routing** | `app/main.py` — decorators like `@app.post()` |
| **Pydantic validation** | `app/models.py` — `HttpUrl` auto-validates URLs |
| **Context managers** | `app/database.py` — `with get_cursor() as cur:` |
| **Multi-stage Docker** | `Dockerfile` — builder stage vs runtime stage |
| **Docker health checks** | `docker-compose.yml` — `healthcheck` blocks |
| **Persistent volumes** | `docker-compose.yml` — `pgdata` and `redisdata` |
| **Service dependencies** | `docker-compose.yml` — `depends_on` with conditions |
| **Cache-aside pattern** | `app/main.py` — Redis check → DB fallback → cache result |
| **Redis TTL** | `app/cache.py` — `setex()` with expiry |
| **SQL indexes** | `app/main.py` — `CREATE INDEX` on startup |
