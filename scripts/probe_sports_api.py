import json
import re
import requests

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.kleague.com/schedule.do?leagueId=1"}
html = requests.get("https://www.kleague.com/schedule.do?leagueId=1", headers=headers, timeout=20).text
# extract JSON.stringify payload near getScheduleList
idx = html.find("getScheduleList.do")
chunks = []
for i in range(max(0, idx - 2000), min(len(html), idx + 8000)):
    pass
block = html[idx : idx + 6000]
# find data: or JSON.stringify(
for m in re.finditer(r"JSON\.stringify\((\{[^}]+\})\)", block):
    print("payload candidate:", m.group(1)[:500])
for m in re.finditer(r'"meetYear"\s*:\s*[^,]+', block):
    print("field", m.group(0))

# dump ajax block to file
with open("c:/WorkSpace/japantour_project/data/cache/kleague_ajax_snippet.txt", "w", encoding="utf-8") as f:
    f.write(block)
