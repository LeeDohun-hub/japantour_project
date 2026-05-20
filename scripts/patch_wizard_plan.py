"""One-off patch: replace plan renderer block in wizard.js."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIZ = ROOT / "frontend" / "wizard.js"
text = WIZ.read_text(encoding="utf-8")
start = text.index("// ── PLAN HTML RENDERER")
end = text.index("const _LEAGUE_LABELS = {")
new_block = Path(__file__).with_name("wizard_plan_block.js").read_text(encoding="utf-8")
WIZ.write_text(text[:start] + new_block + text[end:], encoding="utf-8")
print("patched wizard.js")
