"""One-time helper: turns a short-lived user token into a long-lived Page token and saves it to .env.

Put FB_APP_ID, FB_APP_SECRET and FB_USER_TOKEN into .env first, then run:
    python get_page_token.py
"""
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV = Path(__file__).parent / ".env"
GRAPH = "https://graph.facebook.com/v21.0"

load_dotenv(ENV)


def get(path: str, **params) -> dict:
    r = requests.get(f"{GRAPH}/{path}", params=params, timeout=30)
    if not r.ok:
        sys.exit(f"Facebook error: {r.text}")
    return r.json()


def set_env(key: str, value: str) -> None:
    text = ENV.read_text(encoding="utf-8")
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    else:
        text += f"\n{line}\n"
    ENV.write_text(text, encoding="utf-8")


long_user = get(
    "oauth/access_token",
    grant_type="fb_exchange_token",
    client_id=os.environ["FB_APP_ID"],
    client_secret=os.environ["FB_APP_SECRET"],
    fb_exchange_token=os.environ["FB_USER_TOKEN"],
)["access_token"]

pages = get("me/accounts", access_token=long_user)["data"]
if not pages:
    sys.exit("No pages found. Check that you are a Page admin and granted pages_show_list.")

for i, p in enumerate(pages):
    print(f"{i}: {p['name']} (id {p['id']})")
choice = pages[int(input("Page number: ")) if len(pages) > 1 else 0]

set_env("FB_PAGE_ID", choice["id"])
set_env("FB_PAGE_TOKEN", choice["access_token"])
print(f"Saved FB_PAGE_ID and FB_PAGE_TOKEN for '{choice['name']}' to .env")
