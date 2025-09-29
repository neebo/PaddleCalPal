import gspread, os, json

from oauth2client.service_account import ServiceAccountCredentials

def getAllExistingRaces():
    """Read all existing race titles from the Google Sheet."""

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
    title_col = sheet.find("Title").col
    all_titles = sheet.col_values(title_col)
    return all_titles
