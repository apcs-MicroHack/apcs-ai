import json
from pathlib import Path
from typing import Dict, Optional


def _token_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    token_dir = root / "src" / "db"
    token_dir.mkdir(parents=True, exist_ok=True)
    return token_dir / "runtime_tokens.json"


def load_tokens() -> Dict[str, str]:
    path = _token_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_tokens(
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    csrf_token: Optional[str] = None,
) -> None:
    tokens = load_tokens()
    if access_token:
        tokens["API_ACCESS_TOKEN"] = access_token
    if refresh_token:
        tokens["API_REFRESH_TOKEN"] = refresh_token
    if csrf_token:
        tokens["API_CSRF_TOKEN"] = csrf_token

    _token_path().write_text(json.dumps(tokens), encoding="utf-8")


def clear_tokens() -> None:
    path = _token_path()
    if path.exists():
        path.unlink()
