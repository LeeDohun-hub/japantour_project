import json
from pathlib import Path
import requests

h = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json; charset=utf-8",
    "Referer": "https://www.kleague.com/schedule.do?leagueId=1",
    "Origin": "https://www.kleague.com",
}
url = "https://www.kleague.com/getScheduleList.do"
out = Path("data/cache/kleague_samples.json")

samples = {}
for year in ("2025", "2026"):
    for month in [f"{m:02d}" for m in range(1, 13)]:
        b = {"year": year, "month": month, "leagueId": "1", "etcYn": "N"}
        r = requests.post(url, headers=h, json=b, timeout=20)
        d = r.json()
        sl = (d.get("data") or {}).get("scheduleList") or []
        if sl:
            samples[f"{year}-{month}"] = sl[:2]

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
print("months with data", list(samples.keys()))
