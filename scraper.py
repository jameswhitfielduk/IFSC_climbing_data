from selenium import webdriver  # Main Selenium API used to drive the browser.
from selenium.webdriver.common.by import By  # Locator strategies (CLASS_NAME, XPATH, etc.).
from selenium.webdriver.support.ui import WebDriverWait  # Explicit wait utility for dynamic pages.
from selenium.webdriver.support import expected_conditions as EC  # Wait conditions used with WebDriverWait.
from selenium.webdriver.chrome.options import Options  # Chrome-specific startup options.
from selenium.common.exceptions import NoSuchElementException, TimeoutException  # Exception handling for missing elements during extraction.
from pathlib import Path  # Used to manage file paths for output CSV.
import numpy as np  # Generates the year range for iteration.
import time  # Adds a short fixed delay after year selection.
import pandas as pd  # Builds and exports the final table.

WAIT_SECONDS = 10
URL = "https://ifsc.results.info/"
OUTPUT_DIR = Path("new_raw_data")
OUTPUT_FILE = OUTPUT_DIR / "events_data.csv"

# Configure how Chrome is launched for the whole scraping session.
chrome_options = Options()
# Run without opening a visible browser window.
#chrome_options.add_argument("--headless")


# Open the year dropdown so year options become visible/clickable.
def open_dropdown(driver, wait):
    # Wait until the dropdown input is clickable.
    dropdown_button = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".season-selector .el-input__inner"))
    )
    # Click the dropdown to reveal year entries.
    dropdown_button.click()
    # Return to caller after UI state is updated.
    return

# Click the requested year after opening the dropdown.
def click_on_year(driver, wait, year):
    open_dropdown(driver, wait)

    # Wait until at least one dropdown list is visible.
    wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".el-scrollbar__view.el-select-dropdown__list li span")
        )
    )

    # Scan all visible options and click the matching year.
    options = driver.find_elements(
        By.CSS_SELECTOR, ".el-scrollbar__view.el-select-dropdown__list li span"
    )
    for option in options:
        if option.text.strip() == year:
            option.click()
            print(f"Clicked on {year}")
            return

    raise ValueError(f"Year option not found in dropdown: {year}")

def extract_event_rows(driver):
    # Prefer link-first extraction and filter for event-like URLs.
    # Look for links that contain an event ID number, usually structured like /event/1234
    link_elements = driver.find_elements(By.CSS_SELECTOR, "a.event-card[href*='/event/']") 
    rows = []
    seen = set()

    for link in link_elements:
        href = link.get_attribute("href")
        if not href or href in seen:
            continue

        title = ""

        try:
            # Look inside the link for the exact div holding the title
            title_element = link.find_element(By.CSS_SELECTOR, "div.font-weight-bold.h5.mb-0")
            title = title_element.text.strip()
            
            # Fallback just in case Vue.js renders it in a way Selenium thinks is "invisible"
            if not title:
                title = title_element.get_attribute("innerText").strip()
                
        except NoSuchElementException:
            title = "Title extraction failed"

        seen.add(href)
        rows.append((title, href))

    return rows

# Collect all rows before creating the DataFrame at the end.
data = []

# Build year labels from 1990 through 2024. Temporarily set to 1990-1991 for testing. Adjust the end year as needed for full scraping.
years = [str(i) for i in np.arange(1990,1992,1)]

# Start one Chrome WebDriver instance used by all functions below.
driver = webdriver.Chrome(options=chrome_options)
wait = WebDriverWait(driver, WAIT_SECONDS)

# Load the site before interacting with dropdowns and event elements.
try: 
    driver.get(URL)

# Loop over each year, scrape event names/links, and append to data.
    for year in years:
        try:
            click_on_year(driver, wait, year)

            # Wait for the loading mask to appear, then disappear
            wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "el-loading-mask")))
            # static wait to allow Vue.js to physically render the DOM elements
            # This is safer than relying on a CSS selector that might change year-to-year
            time.sleep(0.5)

            # Extract the stable rows
            rows = extract_event_rows(driver)
            if len(rows) == 0:
                print(f"{year}: No event links found on page.")
            else:
                print(f"{year}: extracted {len(rows)} rows")
            
            for title, href in rows:
                data.append(
                    {
                        "Year": year,
                        "Event Title": title,
                        "Href": href,
                    }
                )

        except (TimeoutException, ValueError) as ex:
            print(f"Skipping year {year}: {ex}")
            continue

finally:
    driver.quit() # Close browser session after scraping is complete.

# Convert collected row dictionaries into a tabular DataFrame.
df = pd.DataFrame(data)
# Ensure output directory exists.
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# Export results to CSV in the specified output directory.
df.to_csv(OUTPUT_FILE, index=False)
# Print first few rows for a quick sanity check.
print(df.head())
# Print last few rows to inspect the end of the dataset.
print(df.tail())