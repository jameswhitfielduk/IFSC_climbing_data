from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd

def check(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode

    driver = webdriver.Chrome(options=chrome_options)

    driver.get(url)
    time.sleep(5)
    try:
        event_name = driver.find_element(By.XPATH,'//h4[@CLASS="text-center mt-5 mb-5"]').text
        if "finished" in event_name:
            print(f'f{url}')
            return
        else:
            print(f'{url}')
    except:
        print(f'{url}')
    return

url =  'https://ifsc.results.info/event/1177/general/lead'


with open("third_list_url.txt", "r") as file:
    url_list = [line.strip() for line in file]
url_list = url_list[:-1]
for i in url_list:
    check(i)
