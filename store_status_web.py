#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from scrape_cm_soup_stores import (
    check_product_for_store,
    extract_product_id,
    find_store_ids_by_name,
    get_store_id_map,
)


HOST = "127.0.0.1"
PORT = 8000
HTML_SNAPSHOT = Path(
    "Central Market Green Chile Chicken Soup, 16 oz _ Central Market - Really Into Food.htm"
)
TARGET_STORES = ["Plano", "Lovers Lane"]


def collect_status() -> dict:
    html_text = HTML_SNAPSHOT.read_text(encoding="utf-8", errors="ignore")
    product_id = extract_product_id(html_text)
    store_map = get_store_id_map()
    target_store_ids = find_store_ids_by_name(TARGET_STORES, store_map)

    stores = []
    title = None
    for label, store_id in target_store_ids.items():
        product = check_product_for_store(product_id, store_id)
        title = title or product["title"]
        stores.append(
            {
                "label": label,
                "store_id": store_id,
                "located": bool(product["in_assortment"]),
                "in_stock": bool(product["available"]),
            }
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "product_id": product_id,
        "title": title,
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
    .wrap {
      max-width: 920px;
      margin: 0 auto;
      padding: 28px 20px 44px;
    }
    .hero {
      border: 1px solid var(--line);
      background: var(--card);
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    }
    h1 {
      margin: 0 0 8px;
      font-size: clamp(1.5rem, 3vw, 2.2rem);
      line-height: 1.2;
      color: var(--brand);
    }
    .meta {
      margin: 0;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      color: #4b544d;
      font-size: 0.95rem;
    }
    .actions {
      margin-top: 14px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    button {
      border: 0;
      background: var(--brand);
      color: white;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: 0.95rem;
      padding: 10px 14px;
      border-radius: 10px;
      cursor: pointer;
    }
    .grid {
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--card);
      padding: 14px;
    }
    .card h2 {
      margin: 0 0 8px;
      font-size: 1.15rem;
      color: var(--brand);
    }
    .row {
      margin: 6px 0;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: 0.95rem;
    }
    .yes { color: var(--ok); font-weight: 700; }
    .no { color: var(--no); font-weight: 700; }
    .error {
      margin-top: 14px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid #e8bcbc;
      background: #fff3f3;
      color: #8d2f2f;
      display: none;
      font-family: "Trebuchet MS", Verdana, sans-serif;
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1 id="title">Loading soup status...</h1>
      <p class="meta" id="meta"></p>
      <div class="actions">
        <button id="refresh">Refresh</button>
      </div>
      <div id="grid" class="grid"></div>
      <div id="error" class="error"></div>
    </section>
  </main>
  <script>
    async function loadStatus() {
      const errorEl = document.getElementById("error");
      errorEl.style.display = "none";
      try {
        const res = await fetch("/api/status");
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();

        document.getElementById("title").textContent = data.title || "Soup status";
        const generated = new Date(data.generated_at_utc);
        document.getElementById("meta").textContent =
          "Product ID: " + data.product_id + " | Updated: " + generated.toLocaleString();

        const grid = document.getElementById("grid");
        grid.innerHTML = "";
        for (const store of data.stores) {
          const card = document.createElement("article");
          card.className = "card";
          card.innerHTML = `
            <h2>${store.label} (#${store.store_id})</h2>
            <p class="row">Located: <span class="${store.located ? "yes" : "no"}">${store.located ? "YES" : "NO"}</span></p>
            <p class="row">In Stock: <span class="${store.in_stock ? "yes" : "no"}">${store.in_stock ? "YES" : "NO"}</span></p>
          `;
          grid.appendChild(card);
        }
      } catch (err) {
        const errorEl = document.getElementById("error");
        errorEl.textContent = "Could not load store status: " + err.message;
        errorEl.style.display = "block";
      }
    }

    document.getElementById("refresh").addEventListener("click", loadStatus);
    loadStatus();
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
                body = json.dumps({"error": str(exc)}).encode("utf-8")
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
    server = HTTPServer((HOST, PORT), Handler)
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
