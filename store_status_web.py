#!/usr/bin/env python3
import json
import os
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
GRAPHQL_URL = "https://services.centralmarket.com/cm-graphql-service/"
PRODUCT_PAGE_URL = os.getenv(
    "PRODUCT_PAGE_URL",
    "https://www.centralmarket.com/product/central-market-green-chile-chicken-soup-16-oz/608890",
)
TARGET_STORES = [
    ("Plano", 546),
    ("Lovers Lane", 552),
]


def product_id_from_product_url() -> int:
    parsed = urlparse(PRODUCT_PAGE_URL)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise ValueError(f"Invalid PRODUCT_PAGE_URL path: {PRODUCT_PAGE_URL}")
    product_id_part = parts[-1]
    if not product_id_part.isdigit():
        raise ValueError(
            f"Could not extract numeric product id from PRODUCT_PAGE_URL: {PRODUCT_PAGE_URL}"
        )
    return int(product_id_part)


def gql(query: str, variables: dict | None = None) -> dict:
    payload = {"query": query, "variables": variables or {}}
    req = Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            ),
            "Origin": "https://www.centralmarket.com",
            "Referer": "https://www.centralmarket.com/",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GraphQL HTTPError {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"GraphQL URLError: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"GraphQL request failed: {exc}") from exc

    if "errors" in body:
        raise RuntimeError(f"GraphQL response errors: {body['errors']}")
    if "data" not in body:
        raise RuntimeError(f"GraphQL missing data payload: {body}")
    return body["data"]


def with_retry(fn, attempts: int = 3, delay_seconds: float = 0.8):
    last_exc = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i < attempts - 1:
                time.sleep(delay_seconds * (i + 1))
    raise RuntimeError(f"Operation failed after {attempts} attempts: {last_exc}") from last_exc


def check_product_for_store(product_id: int, store_id: int) -> dict:
    query = """
    query ProductByStore($productId: Int!, $storeId: Int!) {
      product(productId: $productId, storeId: $storeId) {
        title
        in_assortment
        available
      }
    }
    """
    data = gql(query, {"productId": product_id, "storeId": store_id})
    product = data.get("product")
    if not product:
        raise RuntimeError(f"No product payload for product={product_id}, store={store_id}")
    return product


def collect_status() -> dict:
    product_id = product_id_from_product_url()
    stores = []
    title = None

    for label, store_id in TARGET_STORES:
        product = with_retry(lambda: check_product_for_store(product_id, store_id))
        title = title or product.get("title")
        stores.append(
            {
                "label": label,
                "store_id": store_id,
                "located": bool(product.get("in_assortment")),
                "in_stock": bool(product.get("available")),
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "product_id": product_id,
        "title": title or "Central Market Green Chile Chicken Soup, 16 oz",
        "source": GRAPHQL_URL,
        "product_page_url": PRODUCT_PAGE_URL,
        "stores": stores,
    }


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Soup Store Checker</title>
  <style>
    :root {
      --bg: #f4f1e8;
      --ink: #1f2a1f;
      --brand: #1f6b4f;
      --card: #fffdfa;
      --ok: #1f7a41;
      --no: #a83232;
      --line: #d8d2c4;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Georgia", "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(1400px 600px at 20% -10%, #d7e8d8 0%, transparent 70%),
        radial-gradient(1200px 600px at 110% 0%, #f0dfc8 0%, transparent 70%),
        var(--bg);
    }
    .wrap { max-width: 920px; margin: 0 auto; padding: 28px 20px 44px; }
    .hero {
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 10px 30px rgba(0,0,0,.08);
    }
    h1 { margin: 0 0 8px; font-size: clamp(1.5rem,3vw,2.2rem); line-height: 1.2; color: var(--brand); }
    .meta { margin: 0; font-family: "Trebuchet MS", Verdana, sans-serif; color: #4b544d; font-size: .95rem; }
    .actions { margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; }
    button {
      border: 0; background: var(--brand); color: #fff; font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: .95rem; padding: 10px 14px; border-radius: 10px; cursor: pointer;
    }
    .grid { margin-top: 18px; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap: 14px; }
    .card { border: 1px solid var(--line); border-radius: 14px; background: var(--card); padding: 14px; }
    .card h2 { margin: 0 0 8px; font-size: 1.15rem; color: var(--brand); }
    .row { margin: 6px 0; font-family: "Trebuchet MS", Verdana, sans-serif; font-size: .95rem; }
    .yes { color: var(--ok); font-weight: 700; }
    .no { color: var(--no); font-weight: 700; }
    .error {
      margin-top: 14px; padding: 10px 12px; border-radius: 10px; border: 1px solid #e8bcbc;
      background: #fff3f3; color: #8d2f2f; display: none; font-family: "Trebuchet MS", Verdana, sans-serif;
      white-space: pre-wrap;
    }
    .site-footer {
      margin-top: 14px;
      text-align: center;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: .95rem;
      color: #4b544d;
    }
    .site-footer a {
      color: var(--brand);
      font-weight: 700;
      text-decoration: none;
    }
    .site-footer a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1 id="title">Loading soup status...</h1>
      <p class="meta" id="meta"></p>
      <p class="meta">Auto-refresh: every 5 minutes</p>
      <div class="actions"><button id="refresh">Refresh</button></div>
      <div id="grid" class="grid"></div>
      <div id="error" class="error"></div>
    </section>
    <footer class="site-footer">
      Created by dplynn |
      <a href="https://github.com/dplynn/GCC-Checker/tree/main" target="_blank" rel="noopener noreferrer">Repository</a>
    </footer>
  </main>
  <script>
    let isLoading = false;
    async function loadStatus() {
      if (isLoading) return;
      isLoading = true;
      const errorEl = document.getElementById("error");
      errorEl.style.display = "none";
      try {
        const res = await fetch("/api/status");
        let data = null;
        try { data = await res.json(); } catch (_) {}
        if (!res.ok) {
          const serverError = data && data.error ? ("\\n" + data.error) : "";
          throw new Error("HTTP " + res.status + serverError);
        }
        document.getElementById("title").textContent = data.title || "Soup status";
        const generated = new Date(data.generated_at_utc);
        document.getElementById("meta").textContent =
          "Product ID: " + data.product_id + " | Updated: " + generated.toLocaleString() +
          " | Source: live Central Market";
        const grid = document.getElementById("grid");
        grid.innerHTML = "";
        for (const store of data.stores) {
          const card = document.createElement("article");
          card.className = "card";
          card.innerHTML =
            `<h2>${store.label} (#${store.store_id})</h2>` +
            `<p class="row">Located: <span class="${store.located ? "yes" : "no"}">${store.located ? "YES" : "NO"}</span></p>` +
            `<p class="row">In Stock: <span class="${store.in_stock ? "yes" : "no"}">${store.in_stock ? "YES" : "NO"}</span></p>`;
          grid.appendChild(card);
        }
      } catch (err) {
        errorEl.textContent = "Could not load store status: " + err.message;
        errorEl.style.display = "block";
      } finally {
        isLoading = false;
      }
    }
    document.getElementById("refresh").addEventListener("click", loadStatus);
    loadStatus();
    setInterval(loadStatus, 5 * 60 * 1000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))
            return

        if parsed.path == "/api/status":
            try:
                payload = collect_status()
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                print("Error in /api/status:")
                traceback.print_exc()
                body = json.dumps(
                    {
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "product_page_url": PRODUCT_PAGE_URL,
                        "source": GRAPHQL_URL,
                    }
                ).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
