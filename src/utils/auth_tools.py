import os
import requests
from dotenv import load_dotenv, find_dotenv
from src.utils.token_store import save_tokens


load_dotenv(find_dotenv())


def login_and_store_tokens(email: str, password: str) -> bool:
    base_url = os.getenv("API_BASE_URL", "http://10.16.29.94:3000").strip()
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        base_url = f"http://{base_url}"

    url = f"{base_url}/api/auth/login"
    payload = {"email": email, "password": password}

    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"❌ Login failed: {exc}")
        return False

    access_token = resp.cookies.get("access-token")
    refresh_token = resp.cookies.get("refresh-token")
    csrf_token = resp.cookies.get("csrf-token")

    os.environ["API_BASE_URL"] = base_url
    save_tokens(access_token=access_token, refresh_token=refresh_token, csrf_token=csrf_token)

    if access_token:
        os.environ["API_ACCESS_TOKEN"] = access_token
    if refresh_token:
        os.environ["API_REFRESH_TOKEN"] = refresh_token
    if csrf_token:
        os.environ["API_CSRF_TOKEN"] = csrf_token

    return True
