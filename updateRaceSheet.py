import gspread, os, json, datetime
from oauth2client.service_account import ServiceAccountCredentials
from gspread.utils import rowcol_to_a1

def find_and_update_cells(race_title, registrations, schedule, race_contact):
    """Find a race by title in Google Sheet and update registration, schedule, and contact fields."""

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
        cell = sheet.find(race_title)
        update_row = cell.row
        reg_col = sheet.find("Registrations").col
        schedule_col = sheet.find("Schedule").col
        contact_col = sheet.find("Contact Race").col

        updates = [
            {'range': rowcol_to_a1(update_row, reg_col), 'values': [[registrations]]},
            {'range': rowcol_to_a1(update_row, schedule_col), 'values': [[schedule]]},
            {'range': rowcol_to_a1(update_row, contact_col), 'values': [[race_contact]]},
        ]
        sheet.batch_update(updates)

        print(f"✅ Updated '{race_title}' successfully.")
    except gspread.exceptions.CellNotFound:
        print(f"⚠️ Race not found: {race_title}")
    except Exception as e:
        print(f"🚨 Error updating {race_title}: {e}")
