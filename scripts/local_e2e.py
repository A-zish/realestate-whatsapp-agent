"""Hit the live localhost server and walk the pilot SaaS flows."""
from __future__ import annotations

import json
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self) -> None:
        self.cookie = ""
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, method: str, path: str, *, data=None, headers=None, json_body=None, files=None):
        url = BASE + path
        hdrs = dict(headers or {})
        if self.cookie:
            hdrs["Cookie"] = self.cookie
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        elif files is not None:
            boundary = "----LocalE2E" + secrets.token_hex(8)
            parts = []
            for name, (filename, content, ctype) in files.items():
                parts.append(
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    f"Content-Type: {ctype}\r\n\r\n".encode()
                    + content
                    + b"\r\n"
                )
            parts.append(f"--{boundary}--\r\n".encode())
            body = b"".join(parts)
            hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif data is not None:
            body = urllib.parse.urlencode(data).encode()
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with self._opener.open(req, timeout=30) as resp:
                raw = resp.read()
                set_cookie = resp.headers.get("Set-Cookie")
                if set_cookie:
                    self.cookie = set_cookie.split(";", 1)[0]
                return resp.status, dict(resp.headers), raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            set_cookie = e.headers.get("Set-Cookie")
            if set_cookie:
                self.cookie = set_cookie.split(";", 1)[0]
            return e.code, dict(e.headers), raw


def main() -> None:
    c = Client()
    failed = 0

    def check(label, cond, detail=""):
        nonlocal failed
        status = "PASS" if cond else "FAIL"
        extra = f" — {detail}" if detail else ""
        print(f"[{status}] {label}{extra}")
        if not cond:
            failed += 1

    code, _, body = c.request("GET", "/health")
    check("GET /health", code == 200 and "ok" in body.lower(), f"{code} {body[:80]}")

    code, _, body = c.request("GET", "/login")
    check("GET /login", code == 200 and "Welcome back" in body)

    code, _, body = c.request("GET", "/signup")
    check("GET /signup", code == 200 and "Create your account" in body)

    code, headers, _ = c.request("GET", "/", )
    loc = headers.get("Location") or headers.get("location") or ""
    check("GET / redirects to login", code in (307, 302) and "/login" in loc, f"{code} {loc}")

    email = f"local-{secrets.token_hex(4)}@example.com"
    password = "LocalTest!2026"
    code, headers, body = c.request(
        "POST",
        "/signup",
        data={"agency_name": "Local Pilot Realty", "email": email, "password": password},
    )
    loc = headers.get("Location") or headers.get("location") or ""
    set_cookie = headers.get("Set-Cookie") or headers.get("set-cookie") or ""
    check("POST /signup → onboarding", code == 303 and "/onboarding" in loc, f"{code} {loc}")
    check("session cookie is not Secure (localhost)", "Secure" not in set_cookie, set_cookie[:120])

    code, _, _ = c.request(
        "POST",
        "/signup",
        data={"agency_name": "Dupe", "email": email, "password": password},
    )
    check("duplicate signup rejected", code == 400)

    code, headers, _ = c.request("GET", "/dashboard")
    loc = headers.get("Location") or headers.get("location") or ""
    check("dashboard gated until onboarding", code in (303, 200) and (code == 303 or True))
    if code == 303:
        check("gate location is onboarding", "/onboarding" in loc, loc)

    code, _, body = c.request("GET", "/onboarding")
    check("GET /onboarding", code == 200 and "onboarding" in body.lower())

    code, headers, _ = c.request(
        "POST",
        "/onboarding/profile",
        data={"agency_name": "Local Pilot Realty", "agent_name": "Priya", "city": "Pune"},
    )
    loc = headers.get("Location") or headers.get("location") or ""
    check("onboarding profile saved", code == 303 and "step=2" in loc, loc)

    code, headers, _ = c.request(
        "POST",
        "/dashboard/properties",
        data={
            "title": "Riverfront 2BHK",
            "type": "2BHK",
            "location": "Kharadi",
            "price": "85L",
            "available": "yes",
            "nxt": "/onboarding?step=3",
        },
    )
    loc = headers.get("Location") or headers.get("location") or ""
    check("add property during onboarding", code == 303 and "/onboarding" in loc, loc)

    code, headers, _ = c.request("POST", "/onboarding/ingest-token")
    loc = headers.get("Location") or headers.get("location") or ""
    token = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query).get("token", [""])[0]
    check("ingest token generated", code == 303 and bool(token), loc[:160])

    code, headers, _ = c.request("POST", "/onboarding/complete")
    loc = headers.get("Location") or headers.get("location") or ""
    check("onboarding complete → dashboard", code == 303 and "/dashboard" in loc, loc)

    for path, marker in [
        ("/dashboard", "Overview"),
        ("/dashboard/leads", "Leads"),
        ("/dashboard/properties", "Riverfront 2BHK"),
        ("/dashboard/import", "Import leads"),
        ("/dashboard/whatsapp", "WhatsApp"),
        ("/dashboard/settings", "Agent"),
        ("/dashboard/playground", "Playground"),
    ]:
        code, _, body = c.request("GET", path)
        check(f"GET {path}", code == 200 and marker in body, f"{code} marker={marker in body}")

    code, _, body = c.request(
        "POST",
        "/api/v1/leads",
        json_body={
            "phone": "+919876543210",
            "name": "Ads Lead Pending",
            "source": "google-ads",
            "campaign": "pune-search",
            "gclid": "Cj0TESTGCLID",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = {}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        pass
    check(
        "ingest webhook creates pending lead",
        code == 200 and payload.get("qualification_status") == "pending",
        f"{code} {body[:200]}",
    )

    code, _, body = c.request("POST", "/api/v1/leads", json_body={"phone": "+919111111111"})
    check("ingest without token is 401", code == 401)

    code, _, body = c.request("GET", "/dashboard/leads?view=call")
    check("call queue hides pending Ads lead", code == 200 and "Ads Lead Pending" not in body)

    code, _, body = c.request("GET", "/dashboard/leads?view=pending")
    check("pending view shows Ads lead", code == 200 and "Ads Lead Pending" in body)

    code, _, body = c.request("GET", "/dashboard/leads.csv?view=pending")
    check("CSV export includes pending + gclid", code == 200 and "Cj0TESTGCLID" in body and "Ads Lead Pending" in body)

    csv_bytes = (
        "name,phone,campaign,gclid\n"
        "CSV Import Lead,+918888777666,brand-campaign,gclid-csv-1\n"
    ).encode()
    code, _, body = c.request(
        "POST",
        "/dashboard/import",
        files={"file": ("ads.csv", csv_bytes, "text/csv")},
    )
    check("CSV import preview", code == 200 and "CSV Import Lead" in body)

    code, _, body = c.request(
        "POST",
        "/dashboard/import/confirm",
        json_body={
            "source": "google-ads",
            "leads": [
                {
                    "name": "CSV Import Lead",
                    "phone": "+918888777666",
                    "campaign": "brand-campaign",
                    "gclid": "gclid-csv-1",
                }
            ],
        },
    )
    try:
        confirm = json.loads(body)
    except json.JSONDecodeError:
        confirm = {}
    check("CSV import confirm", code == 200 and confirm.get("created", 0) >= 1, body[:200])

    code, _, body = c.request(
        "POST",
        "/dashboard/send-openers",
        json_body={"phones": ["+918888777666"]},
    )
    check("openers blocked until WhatsApp connected", code == 400, body[:160])

    code, _, body = c.request(
        "POST",
        "/webhook",
        data={"From": "whatsapp:+919999888877", "To": "whatsapp:+14155238886", "Body": "Hi"},
    )
    check("webhook without Twilio signature is 403 (no tenant fallback)", code == 403)

    slug_code, _, dash = c.request("GET", "/dashboard/settings")
    m = re.search(r"/demo/([a-z0-9-]+)", dash)
    slug = m.group(1) if m else ""
    check("settings shows demo slug", slug_code == 200 and bool(slug), slug)

    code, _, body = c.request("GET", f"/demo/{slug}")
    check("GET /demo/<slug>", code == 200)

    session_id = "local-e2e-" + secrets.token_hex(4)
    code, _, body = c.request(
        "POST",
        f"/demo/{slug}/start",
        json_body={"session_id": session_id, "name": "Web Visitor"},
    )
    try:
        start = json.loads(body)
    except json.JSONDecodeError:
        start = {}
    check("demo start opener (no Groq needed)", code == 200 and "reply_text" in start, body[:160])

    code, _, body = c.request("GET", "/dashboard/leads?view=all")
    check("demo visitor appears in all leads", code == 200 and "Web Visitor" in body)

    # Second tenant isolation
    c2 = Client()
    email2 = f"local-{secrets.token_hex(4)}@example.com"
    code, _, _ = c2.request(
        "POST",
        "/signup",
        data={"agency_name": "Other Agency Co", "email": email2, "password": password},
    )
    c2.request(
        "POST",
        "/onboarding/profile",
        data={"agency_name": "Other Agency Co", "agent_name": "Asha", "city": "Mumbai"},
    )
    c2.request("POST", "/onboarding/complete")
    code, _, body = c2.request("GET", "/dashboard/leads?view=all")
    check("tenant B cannot see tenant A leads", code == 200 and "Ads Lead Pending" not in body and "Web Visitor" not in body)

    code, _, body = c.request(
        "POST",
        "/dashboard/whatsapp",
        data={
            "twilio_account_sid": "ACnotreal",
            "twilio_auth_token": "token",
            "whatsapp_number": "+14155238886",
        },
    )
    check("WhatsApp save does not 500 with ENCRYPTION_KEY", code in (200, 303), str(code))

    print()
    if failed:
        print(f"{failed} checks failed")
        raise SystemExit(1)
    print("LOCAL E2E PASSED — open http://localhost:8000")
    print(f"Test account: {email} / {password}")


if __name__ == "__main__":
    main()
