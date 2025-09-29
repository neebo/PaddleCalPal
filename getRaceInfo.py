from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def getRaceDetails(race_url):
    """Scrape a PaddleGuru race page for details."""
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    wait = WebDriverWait(driver, 20)

    try:
        # --- Startlist page ---
        startlist_url = f"{race_url}/startlist"
        driver.get(startlist_url)
        wait.until(EC.url_to_be(startlist_url))
        soup = BeautifulSoup(driver.page_source, "html.parser")

        registrations = []
        race_contact, race_title = "", ""

        for div in soup.find_all("div", class_="page-section well"):
            contact_tag = div.find("a", class_="btn btn-default contact")
            if contact_tag and not race_contact:
                race_contact = contact_tag.get("href", "")
                if "=" in race_contact:
                    race_title = race_contact.split("=", 1)[1].strip()

            for a in div.find_all("a", class_=""):
                name = a.text.strip()
                if name:
                    registrations.append(name)

        # --- Schedule page ---
        schedule_url = f"{race_url}/schedule"
        driver.get(schedule_url)
        wait.until(EC.url_to_be(schedule_url))
        soup = BeautifulSoup(driver.page_source, "html.parser")

        schedule = []
        section = soup.find("div", class_="page-section well")
        if section:
            for p in section.find_all("p"):
                text = p.text.strip()
                if text:
                    schedule.append(text)

        return {
            "title": race_title,
            "registrations": registrations,
            "schedule": schedule,
            "contact": race_contact,
        }

    finally:
        driver.quit()
