# IFSC Climbing Data Scraper

## Overview

This project involves a web scraper that extracts data from the IFSC (International Federation of Sport Climbing) results site for all competitions held from 1990 to 2024. The scraper collects event details, results, location, and date for each event and compiles everything into a single CSV file. The process involves handling errors like event cancellations and unexpected refreshes, and the script is optimized using `ThreadPoolExecutor` for efficiency. The final output is stored in '/clean_data/IFSC_climbing_competition_data.csv'. While some initial cleaning has been done, further refinement is still required.

## How It Works

1. **scraper.py**: This script extracts event names, event URLs, and the year of the event, and saves them to a CSV file. This CSV forms the basis of the data collection process.

2. **scrape_one_url.py**: This file contains a function that can be imported into the main notebook (`scrape_each_event.ipynb`). It scrapes all available information for a given event URL.

3. **scrape_location_date.py**: This script extracts the location and date for each event.

4. **scrape_each_event.ipynb**: This Jupyter Notebook imports functions from the other Python files. It handles the main scraping workflow, loops through event URLs, and appends all possible modalities (e.g., boulder, lead, speed, combined). The notebook is designed to handle various error scenarios. (unfortunately i didn't store all the process, i only have the final version)

5. **check_cancel.py**: This script checks if any event was cancelled.

6. **last_problem.py**: This script addresses the remaining issues, which later i came to realize was due to some modalities displaying 'Rounds for this category not finished yet', an event that actually did not happen and neither will.

## Workflow

1. **Extract Event Data**: 
   - The first script scrapes all events for each year and stores them in a CSV with columns: `year`, `event_name`, and `url`.
   - For each event URL, i appended `/general/{modality}`, where `modality` can be `boulder`, `lead`, `speed`, `combined`, or `boulder&lead`.

2. **Scrape Event Results**:
   - For each event URL, the script loops through all possible modality URLs and attempts to extract results. If the results page exists, it scrapes all available data.
   - The process is optimized using `ThreadPoolExecutor` for parallel processing.

3. **Error Handling**:
   - The script prints URLs that encountered errors, and each error is analyzed to determine whether it was due to a random issue (like a page refresh) or a more persistent issue (like a cancelled event). These errors are addressed appropriately.

4. **Location and Date Extraction**:
   - Once event results are scraped, i extracted the location and date for each event using the `scrape_location_date.py` script.

5. **Data Cleaning and Merging**:
   - All data is concatenated and merged into a single CSV file.
   - Duplicate column names (e.g., 'Semi-Final' vs. 'Semi-final') are handled, and the `athlete_number` column is cleaned, removing any extraneous symbols and ensuring that the values are numeric.

## Requirements

- Python 3.11.9
- Selenium
- Pandas
- ThreadPoolExecutor (concurrent.futures)
- tqdm (for progress bars)


