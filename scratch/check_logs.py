import requests
import json

try:
    r = requests.get("http://localhost:8080/api/bot/logs?last=60", timeout=5)
    logs = r.json()
    if not logs:
        print("No logs captured yet. Bot has not been started.")
    for l in logs:
        level = l.get("level", "info").upper()
        ts = l.get("ts", "")
        msg = l.get("msg", "")
        print(f"[{level}] {ts} - {msg}")
except Exception as e:
    print(f"Could not reach backend: {e}")
