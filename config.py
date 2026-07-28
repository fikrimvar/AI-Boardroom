import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".yz_panel"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"

DEFAULT_CONFIG = {
    "api_keys": {
        "anthropic": "",
        "openai": "",
        "gemini": "",
        "groq": "",
        "openrouter": ""
    },
    "rounds": 2,
    "personas": [
        {
            "name": "Mimar",
            "role": "Sistem mimarı, performans ve veritabanı uzmanı. Sağlam altyapı tasarlar.",
            "provider": "gemini",
            "model": "gemini-2.5-flash"
        },
        {
            "name": "Eleştirmen",
            "role": "Kritik yaklaşım sergileyen, güvenlik açıklarını ve mantık hatalarını yakalayan uzman.",
            "provider": "groq",
            "model": "llama-3.3-70b-versatile"
        },
        {
            "name": "Ürün-UX",
            "role": "Kullanıcı deneyimi, akış hızı ve işlevsellik odaklı ürün yöneticisi.",
            "provider": "openrouter",
            "model": "deepseek/deepseek-chat"
        }
    ]
}

def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "api_keys" not in data:
                data["api_keys"] = DEFAULT_CONFIG["api_keys"]
            else:
                for k in DEFAULT_CONFIG["api_keys"]:
                    if k not in data["api_keys"]:
                        data["api_keys"][k] = ""
            if "rounds" not in data:
                data["rounds"] = 2
            if "personas" not in data:
                data["personas"] = DEFAULT_CONFIG["personas"]
            return data
    except Exception:
        return DEFAULT_CONFIG

def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
