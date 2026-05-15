import concurrent.futures
import time
import urllib.request


def make_request():
    try:
        with urllib.request.urlopen("http://localhost:8000/api/health") as r:
            return r.status
    except Exception:
        return 500


print("🚀 Starting load test (50 concurrent workers, 500 requests)...")
start = time.time()

with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
    futures = [executor.submit(make_request) for _ in range(10000)]
    results = [f.result() for f in futures]

duration = time.time() - start
print(f"⏱️ Done in {duration:.2f} seconds")
print(f"✅ Success (200): {results.count(200)}")
print(f"❌ Failed: {len(results) - results.count(200)}")
print(f"📊 Requests/sec: {500 / duration:.2f}")
