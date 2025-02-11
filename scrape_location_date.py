from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

df = pd.read_csv('./raw_extracted_data/events_data.csv')
urls = df['Href'].values

chrome_options = Options()
chrome_options.add_argument("--headless")

loc_list = []
date_list = []

#Function to scrape data for a single URL
def scrape_url(url):
    loc, date = None, None  #Default values in case of error
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, '//div[@CLASS="flex-fill ml-3"]'))
        )

        #Find the location element (ensure it's available)
        loc_elements = driver.find_elements(By.XPATH, '//div[@CLASS="flex-fill ml-3"]')
        if len(loc_elements) > 0:
            loc = loc_elements[0].find_element(By.TAG_NAME, 'div').get_attribute('innerHTML').strip()

        #Find the date element (ensure it's available)
        if len(loc_elements) > 1:
            date = loc_elements[1].find_element(By.TAG_NAME, 'div').get_attribute('innerHTML').strip()

        loc_list.append(loc)
        date_list.append(date)
        
    except Exception as e:
        print(f"Error loading data from {url}: {e}")
        loc_list.append(None)
        date_list.append(None)
    finally:
        if driver:
            driver.quit()  
    return loc, date

with ThreadPoolExecutor(max_workers=5) as executor:
    results = list(tqdm(executor.map(scrape_url, urls), total=len(urls)))


df_result = pd.DataFrame({
    'Local': loc_list,
    'Date': date_list,
    'Href': urls
})


df_result.to_csv('./clean_dat/local_date.csv', index=False)

print("Scraping complete, data saved to './clean_data/local_date.csv'.")
