"""Scrape PaddleGuru for upcoming California races open to outrigger or surfski.

Outputs:
  docs/races.json                    machine-readable list (read by the weekly Claude task)
  docs/california-oc-surfski.ics     calendar feed you can subscribe to in Google Calendar
  debug/                             page HTML and captured JSON, uploaded as a workflow artifact

PaddleGuru builds its race list with JavaScript, so this drives a real (headless)
Chromium via Playwright. It also records any JSON the page loads, which makes it easy
to switch to a direct API call later if PaddleGuru exposes one.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from dateutil import parser as dateparser

ROOT = "https://paddleguru.com"
LIST_URL = f"{ROOT}/races?search=&sport=all"
OUT_DIR = Path("docs")
DEBUG_DIR = Path("debug")

CA_PAT = re.compile(r"\b(California|CA)\b(?!\w)")
CRAFT_PAT = re.compile(
    r"surf\s*-?\s*ski|outrigger|\bva['’]?a\b|\bOC\s*-?\s*[126]\b|\bV\s*-?\s*[16]\b",
    re.I,
)
MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE_PAT = re.compile(
    rf"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+20\d\d",
    re.I,
)
RACE_HREF = re.compile(r"^/races/[^/?#]+/?$")


@dataclass
class Race:
    name: str
    url: str
    date: str | None = None          # ISO yyyy-mm-dd
    location: str | None = None
    crafts: list[str] = field(default_factory=list)
    california: bool = False


# ---------- text parsing helpers (pure, unit-testable) ----------

def find_date(text: str, today: date | None = None) -> date | None:
    """Return the earliest date found in the text that is today or later."""
    today = today or date.today()
    found = []
    for m in DATE_PAT.finditer(text):
        raw = re.sub(r"(\d)(st|nd|rd|th)", r"\1", m.group(0))
        try:
            found.append(dateparser.parse(raw, fuzzy=True).date())
        except (ValueError, OverflowError):
            continue
    upcoming = sorted(d for d in found if d >= today)
    return upcoming[0] if upcoming else None


def find_crafts(text: str) -> list[str]:
    labels = set()
    for m in CRAFT_PAT.finditer(text):
        t = m.group(0).lower().replace(" ", "").replace("-", "")
        if "ski" in t:
            labels.add("surfski")
        else:
            labels.add("outrigger")
    return sorted(labels)


def find_location(text: str) -> str | None:
    """Best guess at a 'City, ST' style location line."""
    m = re.search(r"([A-Z][A-Za-z .'-]{2,40}),\s*(California|CA)\b", text)
    return f"{m.group(1).strip()}, CA" if m else None


def is_california(text: str) -> bool:
    return bool(CA_PAT.search(text))


# ---------- output ----------

def ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(races: list[Race]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PaddleCalPal//PaddleGuru California OC+Surfski//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:PaddleGuru – California OC & Surfski",
        "X-WR-TIMEZONE:America/Los_Angeles",
    ]
    for r in races:
        if not r.date:
            continue
        d = date.fromisoformat(r.date)
        end = date.fromordinal(d.toordinal() + 1)
        uid = hashlib.sha1(r.url.encode()).hexdigest()[:16] + "@paddlecalpal"
        desc = f"Classes: {', '.join(r.crafts) or 'see race page'}\nRegister/details: {r.url}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
            f"SUMMARY:{ics_escape(r.name)}",
            f"LOCATION:{ics_escape(r.location or 'California')}",
            f"DESCRIPTION:{ics_escape(desc)}",
            f"URL:{r.url}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ---------- scraping ----------

def scrape() -> list[Race]:
    from playwright.sync_api import sync_playwright

    DEBUG_DIR.mkdir(exist_ok=True)
    captured: list[dict] = []

    def on_response(resp):
        ct = resp.headers.get("content-type", "")
        if "json" in ct and "paddleguru" in resp.url:
            try:
                captured.append({"url": resp.url, "body": resp.json()})
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 PaddleCalPal"))
        page.on("response", on_response)

        page.goto(LIST_URL, wait_until="networkidle", timeout=60_000)
        # Load everything if the list grows on scroll or has a "load more" button.
        last_h = 0
        for _ in range(25):
            for label in ("Load more", "Show more", "More races"):
                btn = page.get_by_text(label, exact=False)
                if btn.count() and btn.first.is_visible():
                    btn.first.click()
                    page.wait_for_load_state("networkidle")
            page.mouse.wheel(0, 20_000)
            page.wait_for_timeout(800)
            h = page.evaluate("document.body.scrollHeight")
            if h == last_h:
                break
            last_h = h

        (DEBUG_DIR / "list.html").write_text(page.content())

        # Each race link plus the text of the card around it.
        cards = page.evaluate(
            """() => {
                const out = [];
                const seen = new Set();
                for (const a of document.querySelectorAll('a[href^="/races/"]')) {
                    const href = a.getAttribute('href').split(/[?#]/)[0].replace(/\\/$/, '');
                    if (seen.has(href) || href.split('/').length !== 3) continue;
                    seen.add(href);
                    let el = a, text = '';
                    for (let i = 0; i < 6 && el; i++, el = el.parentElement) {
                        text = el.innerText || '';
                        if (text.length > 60) break;
                    }
                    const title = (a.closest('div')?.querySelector('h3,h2,h4')?.innerText
                                   || a.innerText || '').trim();
                    out.push({href, title, text});
                }
                return out;
            }"""
        )
        print(f"List page: {len(cards)} race links found")
        if not cards:
            (DEBUG_DIR / "captured_json.json").write_text(json.dumps(captured, indent=1)[:5_000_000])
            browser.close()
            # Don't overwrite last week's good output with an empty list.
            raise SystemExit("No race links found on PaddleGuru — page layout may have changed; see debug artifact.")

        races: list[Race] = []
        for c in cards:
            card_text = c["text"]
            # Skip obvious non-California races early when the card shows a state.
            mentions_state = re.search(r",\s*[A-Z]{2}\b|California", card_text)
            if mentions_state and not is_california(card_text):
                continue

            url = ROOT + c["href"]
            texts = [card_text]
            for suffix in ("", "/schedule"):
                try:
                    page.goto(url + suffix, wait_until="networkidle", timeout=45_000)
                    texts.append(page.inner_text("body"))
                except Exception as e:
                    print(f"  ! {url + suffix}: {e}")
            full = "\n".join(texts)

            name = c["title"] or (page.title().split("|")[0].strip() if page else c["href"])
            d = find_date(card_text) or find_date(full)
            race = Race(
                name=name.splitlines()[0][:120],
                url=url,
                date=d.isoformat() if d else None,
                location=find_location(card_text) or find_location(full),
                crafts=find_crafts(full),
                california=is_california(card_text) or is_california(full),
            )
            status = "KEEP" if (race.california and race.crafts and race.date) else "skip"
            print(f"  [{status}] {race.date} {race.name} | {race.location} | {race.crafts}")
            if status == "KEEP":
                races.append(race)

        browser.close()

    (DEBUG_DIR / "captured_json.json").write_text(json.dumps(captured, indent=1)[:5_000_000])
    return sorted(races, key=lambda r: r.date or "")


def main() -> int:
    races = scrape()
    OUT_DIR.mkdir(exist_ok=True)
    payload = {
        "source": LIST_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filter": "California, upcoming, outrigger (OC/V1) or surfski classes",
        "races": [asdict(r) for r in races],
    }
    (OUT_DIR / "races.json").write_text(json.dumps(payload, indent=2) + "\n")
    (OUT_DIR / "california-oc-surfski.ics").write_text(to_ics(races))
    print(f"Wrote {len(races)} races")
    return 0


if __name__ == "__main__":
    sys.exit(main())
