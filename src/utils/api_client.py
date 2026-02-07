"""
Centralized API client helpers: auth headers, token refresh, base URL.
All tool modules import from here instead of duplicating.
"""
import os
import requests
from dotenv import load_dotenv, find_dotenv
from src.utils.token_store import load_tokens, save_tokens

load_dotenv(find_dotenv())


def get_base_url() -> str:
    """Return the normalized backend base URL."""
    base_url = os.getenv("API_BASE_URL", "http://10.16.29.94:3000").strip()
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        base_url = f"http://{base_url}"
    return base_url.rstrip("/")


def get_auth():
    """Return (headers, cookies) dicts with current auth tokens."""
    tokens = load_tokens()
    access_token = (tokens.get("API_ACCESS_TOKEN") or os.getenv("API_ACCESS_TOKEN", "")).strip()
    refresh_token = (tokens.get("API_REFRESH_TOKEN") or os.getenv("API_REFRESH_TOKEN", "")).strip()
    csrf_token = (tokens.get("API_CSRF_TOKEN") or os.getenv("API_CSRF_TOKEN", "")).strip()

    headers = {"Accept": "application/json"}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    cookies = {}
    if access_token:
        cookies["access-token"] = access_token
    if refresh_token:
        cookies["refresh-token"] = refresh_token
    if csrf_token:
        cookies["csrf-token"] = csrf_token

    return headers, cookies


def refresh_tokens() -> bool:
    """Attempt to refresh access token using refresh-token cookie."""
    url = f"{get_base_url()}/api/auth/refresh"
    headers, cookies = get_auth()

    try:
        resp = requests.post(url, headers=headers, cookies=cookies, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"❌ refresh token failed: {exc}")
        return False

    access_token = resp.cookies.get("access-token")
    refresh_token = resp.cookies.get("refresh-token")
    csrf_token = resp.cookies.get("csrf-token")

    save_tokens(access_token=access_token, refresh_token=refresh_token, csrf_token=csrf_token)

    if access_token:
        os.environ["API_ACCESS_TOKEN"] = access_token
    if refresh_token:
        os.environ["API_REFRESH_TOKEN"] = refresh_token
    if csrf_token:
        os.environ["API_CSRF_TOKEN"] = csrf_token

    return True


def api_get(path: str, params: dict = None, timeout: int = 15) -> requests.Response:
    """
    GET request with automatic 401 retry (token refresh).
    Raises on non-2xx after retry.
    """
    url = f"{get_base_url()}{path}"
    headers, cookies = get_auth()

    resp = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=timeout)

    if resp.status_code == 401:
        if refresh_tokens():
            headers, cookies = get_auth()
            resp = requests.get(url, headers=headers, cookies=cookies, params=params, timeout=timeout)

    resp.raise_for_status()
    return resp
