from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
import time
import pandas as pd

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 20)

def scrape_one_url(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode

    driver = webdriver.Chrome(options=chrome_options)

    driver.get(url)
    time.sleep(5)
    try:
        parent = driver.find_element(By.XPATH, '//div[@class="cat-nav"]')
        children = parent.find_elements(By.XPATH, "./*")  # Selects all direct children
        if not children:  
            raise NoSuchElementException
    except:
        #print(f'this modality doesnt exist for this event: {url} ')
        driver.quit()
        return None
    try:    
    
        parent_element = driver.find_element(By.XPATH, '/html/body/div[2]/div[2]/div/div/div[1]/div/div[2]/div')
        #categories é uma lista com os botões das categorias
        categories = parent_element.find_elements(By.TAG_NAME,'div')

        data = []
        modality = driver.find_element(By.XPATH,'//div[@class="gr-discipline-kind"]').text
        event_name = driver.find_element(By.XPATH, '//div[@class="gr-event-name"]').text
        for category in categories:
            category.click()
            time.sleep(3)
            #iterate through rank, name, country, number, semi-final_score and final_score
            parent = driver.find_element(By.CLASS_NAME, 'section-container.desktop') #data is duplicated for mobile
            athletes = parent.find_elements(By.CLASS_NAME, 'athlete-basic-line')
            athlete_count = len(athletes)
            
            #handling first row in athletes, which are the subtitles 'rank', 'athlete' etc
            rank = athletes[0].find_element(By.CLASS_NAME,'rank.cell').text
            name = athletes[0].find_element(By.CLASS_NAME,'athlete.cell').text
            scores = athletes[0].find_element(By.CLASS_NAME,'scores').find_elements(By.CLASS_NAME,'score.quali')
            score_list = []
            
            for score in scores:
                score_list.append(score.find_element(By.TAG_NAME,'a').text)
                
            #if len(athletes) <= 1 it means no athletes competed (data is empty or just with title)
            #then it doesn't enter the loop
            for i in range(athlete_count):
                if i != 0:
                    parent = driver.find_element(By.CLASS_NAME, 'section-container.desktop') #data is duplicated for mobile
                    athlete = parent.find_elements(By.CLASS_NAME, 'athlete-basic-line')[i]
                
                    rank = athlete.find_element(By.CLASS_NAME,'rank').text
                    name = athlete.find_element(By.TAG_NAME,'a').text
                    number_country = athlete.find_element(By.XPATH, './/div[@class="r-name-sub"]')
                    number_country_list = number_country.find_elements(By.TAG_NAME,'span')
                    #in older pages there are no number, so we have to make a flexible code
                
                    if len(number_country_list) == 1:
                        number = ''
                        country = number_country_list[0].text
                    elif len(number_country_list) == 2:
                        number = number_country_list[0].text
                        country = number_country_list[1].text
                    else:
                        print(f'list size of number/country empty or more than 2 values for athlete:{athlete} url:{url}') 
                    scores = athlete.find_element(By.CLASS_NAME,'scores').find_elements(By.CLASS_NAME,'score.quali.cell')
                    score_list1 = []
                    for score in scores:
                        score_list1.append(score.text)
                    #print(rank,name,number,country,score_list1)
                    data.append({
                        'rank':rank,
                        'category': category.text,
                        'modality': modality,
                        'name':name,
                        'number':number,
                        'country':country,
                        'event_name': event_name,
                        **{score_list[i]: score_list1[i] for i in range(len(score_list))}
                    })
    except Exception as e:
        print(f'{url} + {e}')
        driver.quit()
        return None
    else:
        driver.quit()
        return pd.DataFrame(data)

'''url = 'https://ifsc.results.info/event/1341/general/lead'

df = scrape_one_url(url)
print(df.head())'''