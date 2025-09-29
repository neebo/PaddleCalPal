from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from datetime import date
import getAllRacesFromDB

def getRacesToUpdate():
    """Scrape PaddleGuru for races and check which ones already exist in Google Sheet."""
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    wait = WebDriverWait(driver, 10)
    url = "https://paddleguru.com/races"
    root = "https://paddleguru.com"

    try:
        driver.get(url)
        wait.until(EC.url_to_be(url))
        soup = BeautifulSoup(driver.page_source, "html.parser")

        existing_races = getAllRacesFromDB.getAllExistingRaces()
        races_to_update, new_races = [], []

        for item in soup.find_all("div", class_="col-lg-8 col-sm-7"):
            title_tag = item.find("h3", class_="title")
            link_tag = item.find("a")
            if not (title_tag and link_tag):
                continue

            title = title_tag.text.strip()
            link = root + link_tag.get("href")

            if title in existing_races:
                races_to_update.append(link)
            else:
                new_races.append(link)

        print(f"Found {len(races_to_update)} existing races, {len(new_races)} new races.")
        return races_to_update, new_races
    finally:
        driver.quit()
