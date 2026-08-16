"""Offline checks for CSV ingest + rate limiter (no database)."""
from app.importer import parse_leads
from app.ratelimit import RateLimiter


def test_google_ads_headers():
    raw = (
        "Full Name,Phone Number,Campaign,GCLID\n"
        "Riya,+91 9876543210,Search-Jaipur,Cj0KCQ\n"
        "badrow,,Search-Jaipur,\n"
    ).encode()
    parsed = parse_leads("ads.csv", raw)
    assert len(parsed["leads"]) == 1
    lead = parsed["leads"][0]
    assert lead["name"] == "Riya"
    assert lead["phone"].endswith("9876543210")
    assert lead["campaign"] == "Search-Jaipur"
    assert lead["gclid"] == "Cj0KCQ"
    assert parsed["skipped"]


def test_rate_limiter():
    lim = RateLimiter()
    assert lim.allow("k", limit=2, window_s=60)
    assert lim.allow("k", limit=2, window_s=60)
    assert not lim.allow("k", limit=2, window_s=60)


if __name__ == "__main__":
    test_google_ads_headers()
    test_rate_limiter()
    print("pilot ingest/rate checks ok")
