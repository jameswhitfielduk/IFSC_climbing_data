from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import numpy as np
import time
import pandas as pd

chrome_options = Options()
#chrome_options.add_argument("--headless")  # Run in headless mode

url = 'https://ifsc.results.info/event/987/general/boulder'

driver = webdriver.Chrome(options=chrome_options)

driver.get(url)
time.sleep(5)
parent_element = driver.find_element(By.XPATH, '/html/body/div[2]/div[2]/div/div/div[1]/div/div[2]/div')
#categories é uma lista com os botões das categorias
categories = parent_element.find_elements(By.TAG_NAME,'div')

data = []

for categorie in categories:
    categorie.click()
    time.sleep(3)
    #iterate through rank, name, country, number, semi-final_score and final_score
    parent = driver.find_element(By.CLASS_NAME, 'section-container.desktop')
    athletes = parent.find_elements(By.CLASS_NAME, 'athlete-basic-line')
    
    #handling first row in categories, which are the subtitles 'rank', 'athlete' etc
    if categorie == categories[0]:
        rank = athletes[0].find_element(By.CLASS_NAME,'rank.cell').text
        name = athletes[0].find_element(By.CLASS_NAME,'athlete.cell').text
        scores = athletes[0].find_element(By.CLASS_NAME,'scores').find_elements(By.CLASS_NAME,'score.quali')
        score_list = []
        
        for score in scores:
            score_list.append(score.find_element(By.TAG_NAME,'a').text)
        print(rank,name,score_list)
        data.append()
    
    for athlete in athletes[1:]:
        rank = athlete.find_element(By.CLASS_NAME,'rank').text
        name = athlete.find_element(By.TAG_NAME,'a').text
        number_country = athlete.find_element(By.CLASS_NAME,'r-name-sub')
        number_country_list = number_country.find_elements(By.TAG_NAME,'span')
        number = number_country_list[0].text
        country = number_country_list[1].text
        scores = athlete.find_element(By.CLASS_NAME,'scores').find_elements(By.CLASS_NAME,'score.quali.cell')
        scores_list1 = []
        for score in scores:
            scores_list1.append(score.text)
        print(rank,name,number,country,scores_list1)
print(len(athletes))
# Print the text of the element


