
import sys
import re
import requests

BASE_DIR_STR = "C:\\Projects\\adDominum"
sys.path.insert(0, BASE_DIR_STR)

url = "https://www.vatican.va/content/leo-xiv/en/audiences/2026/documents/20260617-udienza-generale.html"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

print("Fetching Vatican.va...")
r = requests.get(url, headers=headers, timeout=20)
print(f"Status: {r.status_code} | Bytes: {len(r.content)}")

# Force UTF-8 decode
try:
    html = r.content.decode("utf-8")
except UnicodeDecodeError:
    html = r.content.decode("latin-1", errors="replace")

# Strip scripts/styles
html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL|re.IGNORECASE)
html = re.sub(r"<style[^>]*>.*?</style>",  "", html, flags=re.DOTALL|re.IGNORECASE)

# Strip HTML tags
text = re.sub(r"<[^>]+>", " ", html)

# Decode entities and normalise quotes
text = text.replace("&nbsp;", " ").replace("&#160;", " ")
text = text.replace("&amp;", "&").replace("&quot;", '"')
text = text.replace("\u2019", "'").replace("\u2018", "'")
text = text.replace("\u201c", '"').replace("\u201d", '"')
text = re.sub(r"\s+", " ", text).strip()

print(f"\nTotal page text length: {len(text)} chars")

# Show last 1500 chars where summary should be
print("\n=== LAST 1500 CHARS OF PAGE TEXT ===")
print(repr(text[-1500:]))

# Search for any mention of "summary" or "Holy Father"
print("\n=== SEARCHING FOR SUMMARY MARKERS ===")
lower = text.lower()
for marker in ["summary", "holy father", "dear brothers and sisters,", 
               "in today", "catechesis"]:
    positions = []
    start = 0
    while True:
        idx = lower.find(marker, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + 1
    if positions:
        print(f"  Found '{marker}' at positions: {positions}")
        # Show context around last occurrence (likely the summary)
        last = positions[-1]
        print(f"  Last occurrence context:")
        print(f"  ...{repr(text[max(0,last-30):last+150])}...")
    else:
        print(f"  NOT FOUND: '{marker}'")
