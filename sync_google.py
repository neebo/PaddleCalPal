"""Push docs/races.json into the "Races" Google Sheet and the California Paddle Races calendar.

Uses the service account in the GOOGLE_CREDENTIALS secret (the same one the old
spreadsheet scripts used). It needs:
  - edit access to the sheet (already granted), and
  - "Make changes to events" on the calendar (Google Calendar → calendar settings →
    Share with specific people → add the service account's email).

Safe to re-run: rows are matched by Race URL and events by a hidden PaddleGuru tag,
so nothing is duplicated. Existing events you added by hand are recognised by date
and name and tagged instead of duplicated. Nothing is ever deleted.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SHEET_ID = os.environ.get("RACES_SHEET_ID", "1Lfm3Yu9GPhRL9V6d_-MMWSQYtdullOq61dNcsq30TRM")
CALENDAR_ID = os.environ.get(
    "RACES_CALENDAR_ID",
    "a75edf8d56ea9c2065eea468796b2c5d859c446d2ce1eed9ebd80e67ba8f3648@group.calendar.google.com",
)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.events",
]
TAG = "paddleguru_url"
TZ = ZoneInfo("America/Los_Angeles")

STOPWORDS = {"paddle", "race", "races", "the", "annual", "series", "of", "and", "a", "at", "in", "on"}


# ---------- pure helpers (unit-tested) ----------

def name_tokens(name: str) -> set[str]:
    s = re.sub(r"\b20\d\d\b|\(.*?\)|#\d+", " ", name.lower())
    words = re.findall(r"[a-z]+", s)
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def same_race(a: str, b: str) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) >= min(2, len(ta), len(tb))


def classes_text(race: dict) -> str:
    return ", ".join(race.get("crafts") or []) or "see race page"


def event_body(race: dict) -> dict:
    d = date.fromisoformat(race["date"])
    end = date.fromordinal(d.toordinal() + 1)
    return {
        "summary": race["name"],
        "location": race.get("location") or "California",
        "description": f"Classes: {classes_text(race)}\nPaddleGuru: {race['url']}",
        "start": {"date": d.isoformat()},
        "end": {"date": end.isoformat()},
        "transparency": "transparent",
        "extendedProperties": {"private": {TAG: race["url"]}},
    }


def sheet_values(race: dict, today: str) -> dict[str, str]:
    """Values for the columns this script manages, keyed by header name."""
    return {
        "Start Date": race["date"],
        "End Date": race["date"],
        "Title": race["name"],
        "Location": race.get("location") or "",
        "Race URL": race["url"],
        "Registration URL": race["url"] + "/register",
        "Description": race.get("notes") or f"Classes: {classes_text(race)}",
        "Updated On": today,
    }


URL_PAT = re.compile(r"https?://[^\s<>\"')]+")


def event_date(ev: dict) -> str | None:
    st = ev.get("start", {})
    return st.get("date") or (st.get("dateTime") or "")[:10] or None


def calendar_only_races(events: list[dict]) -> list[dict]:
    """Upcoming calendar events that didn't come from PaddleGuru (added by hand or by the
    weekly Claude task), shaped like races.json entries so they can go into the sheet."""
    out = []
    for ev in events:
        if ev.get("status") == "cancelled" or ev.get("extendedProperties", {}).get("private", {}).get(TAG):
            continue
        d = event_date(ev)
        if not d or not ev.get("summary"):
            continue
        desc = ev.get("description") or ""
        urls = [u.rstrip(".,") for u in URL_PAT.findall(desc)]
        out.append({
            "name": ev["summary"],
            "date": d,
            "location": ev.get("location") or "",
            "url": urls[0] if urls else ev.get("htmlLink", ""),
            "notes": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", desc)).strip()[:300],
            "source": "calendar",
        })
    return out


def find_row(race: dict, rows: list[list[str]], col: dict[str, int]) -> int | None:
    """Sheet row number (2-based) for this race: same Race URL, else same start date and name."""
    def cell(r, h):
        return r[col[h]] if h in col and len(r) > col[h] else ""
    for n, r in enumerate(rows[1:], start=2):
        if race["url"] and cell(r, "Race URL") == race["url"]:
            return n
    for n, r in enumerate(rows[1:], start=2):
        if cell(r, "Start Date") == race["date"] and same_race(cell(r, "Title"), race["name"]):
            return n
    return None


def plan_events(races: list[dict], existing: list[dict]) -> list[tuple[str, dict, dict | None]]:
    """Return (action, race, existing_event) with action in create / update / tag / ok."""
    by_tag = {
        e.get("extendedProperties", {}).get("private", {}).get(TAG): e
        for e in existing
        if e.get("extendedProperties", {}).get("private", {}).get(TAG)
    }
    plan = []
    for r in races:
        ev = by_tag.get(r["url"])
        if ev:
            # Only the date is kept in sync; titles/locations you edited are left alone.
            moved = ev.get("start", {}).get("date") != r["date"]
            plan.append(("update" if moved else "ok", r, ev))
            continue
        twin = next((e for e in existing
                     if e.get("start", {}).get("date") == r["date"]
                     and same_race(e.get("summary", ""), r["name"])
                     and not e.get("extendedProperties", {}).get("private", {}).get(TAG)), None)
        plan.append(("tag", r, twin) if twin else ("create", r, None))
    return plan


# ---------- Google I/O ----------

def credentials():
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if not raw:
        print("GOOGLE_CREDENTIALS is not set; skipping Google Sheet and Calendar sync.")
        sys.exit(0)
    from google.oauth2.service_account import Credentials
    return Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)


def sync_sheet(creds, races: list[dict]) -> None:
    import gspread
    from gspread.utils import rowcol_to_a1

    ws = gspread.authorize(creds).open_by_key(SHEET_ID).sheet1
    rows = ws.get_all_values()
    header = rows[0] if rows else []
    col = {h.strip(): i for i, h in enumerate(header) if h.strip()}
    if "Race URL" not in col:
        raise SystemExit(f"Sheet '{ws.title}' has no 'Race URL' column; headers are {header}")

    today = datetime.now(TZ).date().isoformat()
    updates, appends = [], []
    for race in races:
        vals = sheet_values(race, today)
        n = find_row(race, rows, col)
        if n:
            for h, v in vals.items():
                if h in col:
                    updates.append({"range": rowcol_to_a1(n, col[h] + 1), "values": [[v]]})
        else:
            row = [""] * len(header)
            for h, v in vals.items():
                if h in col:
                    row[col[h]] = v
            appends.append(row)
            rows.append(row)  # so a duplicate later in this same run matches it
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    if appends:
        ws.append_rows(appends, value_input_option="USER_ENTERED")
    print(f"Sheet '{ws.title}': {len(appends)} added, {len(races) - len(appends)} refreshed")


def sync_calendar(creds, races: list[dict]) -> list[dict]:
    from urllib.parse import quote
    from google.auth.transport.requests import AuthorizedSession

    s = AuthorizedSession(creds)
    base = f"https://www.googleapis.com/calendar/v3/calendars/{quote(CALENDAR_ID)}/events"
    params = {"timeMin": datetime.now(TZ).replace(hour=0, minute=0).isoformat(),
              "singleEvents": "true", "maxResults": "2500"}
    resp = s.get(base, params=params)
    if resp.status_code in (403, 404):
        raise SystemExit(
            "Can't reach the calendar. Share 'California Paddle Races' with the service account "
            f"({creds.service_account_email}) using 'Make changes to events', and make sure the "
            f"Google Calendar API is enabled in its Google Cloud project. ({resp.status_code}: {resp.text[:200]})")
    resp.raise_for_status()
    existing = resp.json().get("items", [])

    counts = {"create": 0, "update": 0, "tag": 0, "ok": 0}
    for action, race, ev in plan_events(races, existing):
        counts[action] += 1
        if action == "create":
            s.post(base, json=event_body(race)).raise_for_status()
            print(f"  + {race['date']} {race['name']}")
        elif action == "update":
            body = event_body(race)
            s.patch(f"{base}/{ev['id']}", json={"start": body["start"], "end": body["end"]}).raise_for_status()
            print(f"  ~ {race['date']} {race['name']} (date changed on PaddleGuru)")
        elif action == "tag":
            desc = ev.get("description") or ""
            if race["url"] not in desc:
                desc = (desc + f"\nPaddleGuru: {race['url']}").strip()
            s.patch(f"{base}/{ev['id']}", json={
                "description": desc,
                "extendedProperties": {"private": {TAG: race["url"]}},
            }).raise_for_status()
            print(f"  = {race['date']} {race['name']} (matched existing '{ev.get('summary')}')")
    print(f"Calendar: {counts['create']} added, {counts['update']} updated, "
          f"{counts['tag']} matched to existing events, {counts['ok']} unchanged")
    after = s.get(base, params=params)
    after.raise_for_status()
    return after.json().get("items", [])


def main() -> int:
    races = [r for r in json.loads(Path("docs/races.json").read_text())["races"] if r.get("date")]
    creds = credentials()
    errors = []

    events: list[dict] = []
    try:
        events = sync_calendar(creds, races)
    except (SystemExit, Exception) as e:  # keep going so the sheet still updates
        errors.append(f"calendar: {e}")
        print(f"!! calendar: {e}")

    # The calendar is the master list: PaddleGuru races plus anything added there by hand
    # or by the weekly Claude task all go into the sheet, one row per race.
    others = calendar_only_races(events)
    print(f"Calendar-only races for the sheet: {len(others)}")
    try:
        sync_sheet(creds, races + others)
    except (SystemExit, Exception) as e:
        errors.append(f"sheet: {e}")
        print(f"!! sheet: {e}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
