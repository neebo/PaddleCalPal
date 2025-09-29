import getAllRacesFromWeb
import updateRaceSheetFromInfo
import addNewRaceToSheet

def update_all_races_online():
    """Fetch races to update and refresh them in Google Sheet."""
    try:
        print("🔍 Checking PaddleGuru for race updates...")
        races_to_update, new_races = getAllRacesFromWeb.getRacesToUpdate()

        if races_to_update:
            print(f"🌀 Updating {len(races_to_update)} existing races...")
            for url in races_to_update:
                updateRaceSheetFromInfo.updateRaceInDB(url)
        else:
            print("✅ No existing races need updates.")

        if new_races:
            print(f"🆕 Found {len(new_races)} new races. Adding them to sheet...")
            for url in new_races:
                addNewRaceToSheet.add_new_race_to_sheet(url)
        else:
            print("📘 No new races found.")

        print("✅ Race update process complete.")

    except Exception as e:
        print(f"🚨 Error during race update process: {e}")

if __name__ == "__main__":
    update_all_races_online()
