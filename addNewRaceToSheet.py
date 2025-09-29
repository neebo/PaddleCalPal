import getRaceInfo
import gspread, os, json
from oauth2client.service_account import ServiceAccountCredentials

def add_new_race_to_sheet(race_url):
    """Fetch details for a new race and add it to the Google Sheet."""

    # Load credentials securely
    scope = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file"
    ]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("Missing GOOGLE_CREDENTIALS environment variable.")

    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds_json), scope)
    client = gspread.authorize(creds)
    sheet = client.open("Races").sheet1

    try:
        data = getRaceInfo.getRaceDetails(race_url)
        if not data or not data.get("title"):
            print(f"⚠️ Skipped {race_url} — no title found.")
            return

        title = data["title"]
        registrations = "\n".join(data.get("registrations", []))
        schedule = "\n".join(data.get("schedule", []))
        contact = data.get("contact", "")
        race_source = "PaddleGuru"
        link = race_url

        # Prepare the row
        new_row = [
            title,
            link,
            race_source,
            registrations,
            schedule,
            contact
        ]

        # Get headers from the sheet
        headers = sheet.row_values(1)

        # If columns are known, we can match — else just append at end
        sheet.append_row(new_row, value_input_option="USER_ENTERED")
        print(f"🆕 Added new race: {title}")

    except Exception as e:
        print(f"🚨 Failed to add {race_url}: {e}")
