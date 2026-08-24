#!/usr/bin/env python3
"""Daily Mercado Livre health check for ZODYAM COMERCIO VAREJISTA LTDA.

Refreshes the OAuth token, pulls recent orders and Mercado Ads campaign
data, compares against the previous day's report, and writes a dated
markdown report under reports/. Run from the repo root.
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_PATH = os.path.join(REPO_ROOT, "credentials.json")
REPORTS_DIR = os.path.join(REPO_ROOT, "reports")
TZ_BR = timezone(timedelta(hours=-3))


def load_creds():
    with open(CREDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_creds(creds):
    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2, ensure_ascii=False)
        f.write("\n")


def git(*args):
    subprocess.run(["git", "-C", REPO_ROOT, *args], check=True)


def http_post_form(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("content-type", "application/x-www-form-urlencoded")
    req.add_header("accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def http_get(url, headers=None):
    req = urllib.request.Request(url, method="GET")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def refresh_token(creds):
    url = "https://api.mercadolibre.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
    }
    resp = http_post_form(url, data)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=resp.get("expires_in", 21600))
    creds["access_token"] = resp["access_token"]
    creds["refresh_token"] = resp["refresh_token"]
    creds["access_token_expires_at"] = expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    creds["updated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return creds


def fetch_orders(access_token, user_id):
    now_br = datetime.now(TZ_BR)
    date_from = (now_br - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    date_to = now_br
    params = {
        "seller": user_id,
        "order.date_created.from": date_from.strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
        "order.date_created.to": date_to.strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
        "sort": "date_desc",
        "limit": 50,
    }
    url = "https://api.mercadolibre.com/orders/search?" + urllib.parse.urlencode(params)
    return http_get(url, {"Authorization": f"Bearer {access_token}"})


def fetch_ads(access_token):
    result = {"advertiser_id": None, "campaigns": None, "error": None}
    try:
        adv = http_get(
            "https://api.mercadolibre.com/advertising/advertisers?product_id=PADS",
            {"Authorization": f"Bearer {access_token}", "Api-Version": "2"},
        )
        advertisers = adv.get("advertisers") or adv.get("results") or []
        if not advertisers:
            result["error"] = f"nenhum advertiser retornado: {adv}"
            return result
        advertiser_id = advertisers[0].get("advertiser_id") or advertisers[0].get("id")
        result["advertiser_id"] = advertiser_id
        campaigns = http_get(
            f"https://api.mercadolibre.com/advertising/product_ads/campaigns"
            f"?advertiser_id={advertiser_id}&limit=50",
            {"Authorization": f"Bearer {access_token}", "Api-Version": "2"},
        )
        result["campaigns"] = campaigns
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}"
    except Exception as e:  # noqa: BLE001
        result["error"] = str(e)
    return result


def previous_report_text():
    if not os.path.isdir(REPORTS_DIR):
        return None
    files = sorted(f for f in os.listdir(REPORTS_DIR) if f.endswith(".md"))
    if not files:
        return None
    with open(os.path.join(REPORTS_DIR, files[-1]), "r", encoding="utf-8") as f:
        return files[-1], f.read()


def summarize_orders(orders_resp):
    if not isinstance(orders_resp, dict):
        return {"error": "resposta inesperada de orders/search"}
    results = orders_resp.get("results", [])
    total = orders_resp.get("paging", {}).get("total", len(results))
    paid = [o for o in results if o.get("status") == "paid"]
    cancelled = [o for o in results if o.get("status") == "cancelled"]
    revenue = sum(o.get("total_amount", 0) for o in paid)
    return {
        "total_orders_in_window": total,
        "orders_fetched": len(results),
        "paid": len(paid),
        "cancelled": len(cancelled),
        "revenue_brl": round(revenue, 2),
    }


def main():
    if not os.path.exists(CREDS_PATH):
        print("credentials.json nao encontrado", file=sys.stderr)
        sys.exit(1)

    creds = load_creds()

    try:
        creds = refresh_token(creds)
    except Exception as e:  # noqa: BLE001
        os.makedirs(REPORTS_DIR, exist_ok=True)
        today = datetime.now(TZ_BR).strftime("%Y-%m-%d")
        with open(os.path.join(REPORTS_DIR, f"{today}.md"), "w", encoding="utf-8") as f:
            f.write(f"# Relatorio {today}\n\nFALHA na renovacao do token: {e}\n")
        print(f"AUTH_FAILED: {e}")
        sys.exit(2)

    save_creds(creds)
    git("add", "credentials.json")
    git("commit", "-m", "chore: refresh token")
    git("push")

    access_token = creds["access_token"]
    user_id = creds["user_id"]

    orders_summary = {"error": None}
    try:
        orders_resp = fetch_orders(access_token, user_id)
        orders_summary = summarize_orders(orders_resp)
    except Exception as e:  # noqa: BLE001
        orders_summary = {"error": str(e)}

    ads = fetch_ads(access_token)

    prev = previous_report_text()

    today = datetime.now(TZ_BR).strftime("%Y-%m-%d")
    now_str = datetime.now(TZ_BR).strftime("%Y-%m-%d %H:%M %Z") or datetime.now(TZ_BR).strftime(
        "%Y-%m-%d %H:%M"
    )

    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"{today}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Relatorio diario ZODYAM - {today}\n\n")
        f.write(f"Gerado em: {now_str} (America/Sao_Paulo)\n\n")
        f.write("## Vendas (ultimas 24h)\n\n")
        f.write("```json\n" + json.dumps(orders_summary, indent=2, ensure_ascii=False) + "\n```\n\n")
        f.write("## Mercado Ads\n\n")
        if ads.get("error"):
            f.write(f"Erro ao consultar Ads: {ads['error']}\n\n")
        else:
            f.write(f"advertiser_id: {ads.get('advertiser_id')}\n\n")
            f.write("```json\n" + json.dumps(ads.get("campaigns"), indent=2, ensure_ascii=False)[:8000] + "\n```\n\n")
        if prev:
            prev_name, prev_text = prev
            f.write(f"## Relatorio anterior ({prev_name}) para comparacao\n\n")
            f.write("```markdown\n" + prev_text[:4000] + "\n```\n")
        else:
            f.write("## Sem relatorio anterior (primeira execucao)\n")

    git("add", "reports/")
    git("commit", "-m", f"docs: relatorio diario {today}")
    git("push")

    print("REPORT_WRITTEN:", report_path)
    print(json.dumps({"orders": orders_summary, "ads_error": ads.get("error")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
