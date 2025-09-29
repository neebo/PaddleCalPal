import getRaceInfo
import updateRaceSheet

def updateRaceInDB(race_url):
    """Fetch race details and update its row in Google Sheet."""
    try:
        data = getRaceInfo.getRaceDetails(race_url)
        if not data or not data.get("title"):
            print(f"⚠️ Skipping {race_url} — no title found.")
            return

        registrations = "\n".join(data.get("registrations", []))
        schedule = "\n".join(data.get("schedule", []))
        contact = data.get("contact", "")

        updateRaceSheet.find_and_update_cells(
            data["title"], registrations, schedule, contact
        )
    except Exception as e:
        print(f"🚨 Failed to update {race_url}: {e}")
