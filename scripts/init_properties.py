"""Seed the Google Sheet `properties` tab from data/properties.json (one-time).

Usage:
    python -m scripts.init_properties

Skips properties whose id already exists in the tab, so it's safe to re-run.
"""
import json
import os

from app import sheets

_JSON = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "properties.json"
)


def main() -> None:
    with open(_JSON, encoding="utf-8") as f:
        seed = json.load(f)

    existing_ids = {p.get("id") for p in sheets.get_properties(only_available=False)}
    added = 0
    for p in seed:
        if p.get("id") in existing_ids:
            print(f"  skip (exists): {p.get('id')}")
            continue
        sheets.add_property(
            {
                "id": p.get("id", ""),
                "title": p.get("title", ""),
                "type": p.get("type", ""),
                "location": p.get("location", ""),
                "price": p.get("price", ""),
                "media_urls": p.get("media_urls", []),
                "available": "yes",
            }
        )
        print(f"  added: {p.get('id')}  {p.get('title')}")
        added += 1

    print(f"\nDone. Added {added} property(ies) to the '{sheets.PROPERTIES_TAB}' tab.")


if __name__ == "__main__":
    main()
