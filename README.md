# 🔗 URL Shortener — Phase 0 Project

## 📝 What This Project Does
This project is a mini **Bitly clone** (URL Shortener). It allows you to take a long URL and generate a short, easy-to-share link. When someone visits the short link, the system redirects them to the original URL.

It uses **Redis** for fast lookups (cache) and **PostgreSQL** for permanent storage.

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
docker compose up --build
```

That's it! All 3 services will start:
- **App/Frontend**: http://localhost:8000
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

### Day 1 — Dev Environment (Using the venv)
```bash
# Run the linter (if you created the .venv)
ruff check app/
mypy app/
```

### Day 2 — Docker
```bash
# See running containers
docker ps

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
\q                     -- quit

# Connect to Redis with redis-cli
docker exec -it url-shortener-redis redis-cli

# Once inside redis-cli:
KEYS *                 -- see all cached keys
GET url:aB3xZ9         -- get a cached URL
QUIT                   -- exit
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
│   ├── utils.py         # Short code generation (base62)
│   ├── static/          # Frontend files (HTML, CSS, JS)
│   └── load_test.py     # Load test script
├── docker-compose.yml   # Orchestrates app + postgres + redis
├── Dockerfile           # Multi-stage build for the FastAPI app
├── requirements.txt     # Python dependencies
├── pyproject.toml       # Ruff, mypy, black configuration
├── .gitignore           # Files to exclude from git
├── .dockerignore        # Files to exclude from Docker build
└── README.md            # This file
```
