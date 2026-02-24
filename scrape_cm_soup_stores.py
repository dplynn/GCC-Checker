#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from urllib import request


GRAPHQL_URL = "https://services.centralmarket.com/cm-graphql-service/"


def extract_product_id(html_text: str) -> int:
    og_match = re.search(
        r'<meta\s+property="og:url"\s+content="https?://[^"]+/[^/]+/(\d+)"',
        html_text,
        re.IGNORECASE,
    )
    if og_match:
        return int(og_match.group(1))

    url_match = re.search(r"/central-market-[^/]+/(\d+)", html_text, re.IGNORECASE)
    if url_match:
        return int(url_match.group(1))

    raise ValueError("Could not find product ID in HTML.")


def gql(query: str, variables: dict | None = None) -> dict:
    payload = {"query": query, "variables": variables or {}}
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        GRAPHQL_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def get_store_id_map() -> dict[str, int]:
    data = gql("query { stores { name store_number } }")
    stores = data["stores"]
    return {s["name"]: int(s["store_number"]) for s in stores}


def find_store_ids_by_name(targets: list[str], all_stores: dict[str, int]) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for target in targets:
        lower_target = target.lower()
        matched = [(name, sid) for name, sid in all_stores.items() if lower_target in name.lower()]
        if not matched:
            raise ValueError(f"No store match found for '{target}'.")
        resolved[target] = matched[0][1]
    return resolved


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
    return data["product"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Central Market soup location for specific stores."
    )
    parser.add_argument(
        "--html",
        default="Central Market Green Chile Chicken Soup, 16 oz _ Central Market - Really Into Food.htm",
        help="Path to saved product HTML file.",
    )
    parser.add_argument(
        "--stores",
        nargs="+",
        default=["Plano", "Lovers Lane"],
        help="Store names to check.",
    )
    args = parser.parse_args()

    html_path = Path(args.html)
    if not html_path.exists():
        print(f"HTML file not found: {html_path}", file=sys.stderr)
        return 1

    html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    product_id = extract_product_id(html_text)
    store_map = get_store_id_map()
    target_store_ids = find_store_ids_by_name(args.stores, store_map)

    print(f"Product ID: {product_id}")
    for store_label, store_id in target_store_ids.items():
        product = check_product_for_store(product_id, store_id)
        located = bool(product["in_assortment"])
        in_stock = bool(product["available"])
        print(
            f"{store_label} (store #{store_id}): "
            f"located={'YES' if located else 'NO'}, "
            f"in_stock={'YES' if in_stock else 'NO'}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
