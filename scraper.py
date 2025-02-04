from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import numpy as np
import time
import pandas as pd

chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode

url = 'https://ifsc.results.info/'

driver = webdriver.Chrome(options=chrome_options)

driver.get(url)

#opens dropdown of years
def open_dropdown():
    dropdown_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CLASS_NAME, "el-input__inner"))
    )
    dropdown_button.click()
    return

#click on the correponding year after opening dropdown
def click_on_year(year): #opens dropdown menu and clicks in the respective year
        open_dropdown()
        elements = driver.find_elements(By.CSS_SELECTOR, ".el-scrollbar__view.el-select-dropdown__list")
        ul_element = elements[2]
        li_elements = ul_element.find_elements(By.TAG_NAME, "li")
        for li in li_elements:
            span = li.find_element(By.TAG_NAME, "span")  # Find the <span> inside each <li>
            if span.text.strip() == year:
                li.click()
                print(f"Clicked on {year}")
                break

data = []
years = [str(i) for i in np.arange(1990,2025,1)]
for year in years:
    eventss = []
    click_on_year(year)
    time.sleep(2)
    #div that contain the events of the selected year
    events_list = driver.find_element(By.XPATH, "/html/body/div[2]/div[2]/div/div/div[1]/div/div[2]/div[2]/div[1]")
    
    #find the element that contains each event text
    events = events_list.find_elements(By.CSS_SELECTOR,'.font-weight-bold.h5.mb-0')
    #loop through event titles and extract text (events title)
    for i in range(len(events)):
        if (i+1) % 3 == 0:
            event = events_list.find_elements(By.CSS_SELECTOR,'.font-weight-bold.h5.mb-0')[i]
            eventss.append(event.text)
            
    #loop to get hrefs
    a_tags = events_list.find_elements(By.TAG_NAME,'a')
    hrefs = [a.get_attribute("href") for a in a_tags]
    print(len(eventss),len(hrefs))
     # Ensure the lengths of event_titles and hrefs match
    if len(eventss) != len(hrefs):
        print(f"Mismatch in data for year {year}: {len(eventss)} titles vs {len(hrefs)} hrefs")
        continue  # Skip this year if there's a mismatch
    # Store data in a list of dictionaries
    for title, href in zip(eventss, hrefs):
        data.append({
            "Year": year,
            "Event Title": title,
            "Href": href
        })
driver.quit()

df = pd.DataFrame(data)
df.to_csv("events_data.csv", index=False)
print(df.head())
print(df.tail())