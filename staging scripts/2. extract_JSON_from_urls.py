# you may need to run 'playwright install' in the terminal to get the browsers

from pathlib import Path
import json
import time
import pandas as pd
from playwright.sync_api import sync_playwright

#### THE AIM OF THIS SCRIPT IS TO:
# 1) Read the list of event URLs from the CSV file (events_data.csv) we created in the previous step (1. extract_event_urls.py) 
# 2) Use Playwright to visit each URL and capture the JSON data returned by the website's API
# 3) Save all the raw JSON data into a JSONL file (one JSON object per line = one event per line) for easy storage and later processing
# 4) Then, we flatten the JSONL into a single CSV file for easier analysis and integration with other datasets.
# 5) Each row in the final CSV represents a unique combination of event, discipline/category (dcat), category round, and stage/route, 
#       with all relevant metadata included as columns.

# import the list of event URLs from the CSV file
BASE = Path("new_raw_data") # the folder path
EVENTS_CSV = BASE / "events_data.csv" # the CSV file we created in the previous step that contains the list of event URLs to scrape
RAW_JSONL = BASE / "all_events_raw.jsonl" # the output JSONL file where we will save the raw JSON data for each event (one JSON object per line)
FLAT_CSV = BASE / "all_events_flat.csv" # the output CSV file where we will save the flattened data

# This function reads the CSV file containing the event URLs, cleans it up by removing duplicates and empty entries, and returns a list of unique, valid URLs to scrape.
def load_event_urls() -> list[str]:
    events_data_urls = pd.read_csv(EVENTS_CSV, usecols=["event_url"])
    urls = events_data_urls["event_url"].dropna().astype(str).str.strip()
    urls = [url for url in urls.unique() if url]
    return urls

# This function uses Playwright to automate a browser, visit each event URL, and capture the JSON data returned by the website's API.
    # by default, it runs in headless mode (no browser window), but you can set headless=False for debugging or if the site blocks headless browsers.
    # It also includes a time delay between requests to avoid overwhelming the server and to mimic more human-like browsing behavior.
def scrape_event_urls_to_jsonl(headless: bool = False, delay_seconds: float = 0.5) -> None:
    event_urls = load_event_urls()
    RAW_JSONL.parent.mkdir(parents=True, exist_ok=True)

    success_count = 0 # counters to keep track of how many requests succeeded vs failed, just for logging purposes
    fail_count = 0

    with sync_playwright() as p:
        # Launch Chromium browser. 
        # If the site still blocks you, change to `headless=False` 
        # so it looks even more like a real human user.
        browser = p.chromium.launch(headless=headless)
        
    # Create a persistent context. This acts like a browser profile and will hold our session cookies automatically.
    # This is important because many sites require you to have an active session (with cookies) to access their APIs
        context = browser.new_context()
        page = context.new_page()

        print("Visiting homepage to establish session and bypass protections...")
        
        # Store the necessary authentication headers here
        api_headers = {
            "Referer": "https://ifsc.results.info/",
            "Origin": "https://ifsc.results.info"
        }
        
        # This sub-function listens to the website's background traffic, so we can capture the API calls it makes when we load the page.
        def intercept_background_requests(request):
            if "/api/v1/" in request.url:
                headers = request.headers
                # If the app uses a Bearer token, we grab it
                if "authorization" in headers:
                    api_headers["Authorization"] = headers["authorization"]
                # also grab any custom security headers (like x-api-key or x-csrf-token)
                for key, value in headers.items():
                    if key.lower().startswith("x-"):
                        api_headers[key] = value

        # Attach a traffic interceptor to the page, so we can extract the necessary headers for authentication using the function above (intercept_background_requests).
        page.on("request", intercept_background_requests)
        
        # Load the main website and wait until the network is quiet, because this means the site has finished loading
        # This forces the website to run its startup routines and make initial API calls, so that we can capture the necessary headers for authentication.
        page.goto("https://ifsc.results.info/", wait_until="networkidle")
        
        print(f"   -> Session established. Using headers: {api_headers}")

        with RAW_JSONL.open("w", encoding="utf-8") as jsonl_file:
            # this loop goes through each event URL we want to scrape, and for each one, it makes a fetch request directly from the page context 
              for i, event_url in enumerate(event_urls, start=1):
                print(f"[{i}/{len(event_urls)}] Fetching {event_url}")

                try:
                    # Use captured headers in case API access depends on dynamic auth context.
                    json_data = page.evaluate(
                        """async ({ url, headers }) => {
                            const response = await fetch(url, { headers });
                            return await response.json();
                        }""",
                        {"url": event_url, "headers": api_headers},
                    )
                except Exception as exc: 
                    # if the request fails for any reason (network error, JSON parsing error, etc), log it and continue to the next URL
                    fail_count += 1
                    print(f"  -> Request failed: {exc}")
                    continue

                if isinstance(json_data, dict) and json_data.get("message") == "Not Authorized!": 
                    # same as above, if the API returns a "Not Authorized" message, log it and continue to the next URL
                    fail_count += 1
                    print("  -> Not Authorized")
                    continue

                if not isinstance(json_data, dict):
                    # if the JSON data is not a dictionary, log it and continue to the next URL
                    fail_count += 1
                    print(f"  -> Skipped unexpected payload type: {type(json_data)}")
                    continue

                json_data["source_event_url"] = event_url # add the source URL to the JSON data, so we know which event it came from when we process it later
                jsonl_file.write(json.dumps(json_data, ensure_ascii=False) + "\n") # write the JSON data to the JSONL file, one line per event
                success_count += 1

                if delay_seconds > 0:
                    time.sleep(delay_seconds) # add a delay between requests to avoid overwhelming the server and to mimic more human-like browsing behavior

        # Close the browser once the loop is finished
        browser.close()

    print("\nFinished.")
    print(f"Saved JSONL to: {RAW_JSONL}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")

# This function reads the raw JSONL file we created in the previous step, and flattens the nested JSON structure into a single CSV file.
def flatten_jsonl_to_csv(input_jsonl: Path = RAW_JSONL, output_csv: Path = FLAT_CSV) -> None:
    if not input_jsonl.exists():
        print(f"JSONL file not found: {input_jsonl}")
        return

    rows = [] # this will hold the flattened rows of data that we will eventually save to the CSV file

    with input_jsonl.open("r", encoding="utf-8") as f:
        # these loops go through each line in the JSONL file (each line is a JSON object representing an event), 
        # and then they navigate through the nested structure of the JSON to extract all relevant information about the event, 
        # its disciplines/categories (dcats), category rounds, stages, and routes.
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                event_payload = json.loads(line) # parse the JSON data for this event. If it fails, log the error and skip to the next line
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSONL line {line_number}: {exc}")
                continue

            # 1st level of the JSON is the event itself, which contains general information about the event and a list of disciplines/categories (dcats)
            event_base = {
                "source_event_url": event_payload.get("source_event_url"),
                "event_id": event_payload.get("id"),
                "event_name": event_payload.get("name"),
                "starts_at": event_payload.get("starts_at"),
                "ends_at": event_payload.get("ends_at"),
                "local_start_date": event_payload.get("local_start_date"),
                "local_end_date": event_payload.get("local_end_date"),
                "location": event_payload.get("location"),
                "country": event_payload.get("country"),
                "timezone": (event_payload.get("timezone") or {}).get("value"),
                "event_type": event_payload.get("type"),
                "league_id": event_payload.get("league_id"),
                "season_id": event_payload.get("season_id"),
            }

            dcats = event_payload.get("dcats") or event_payload.get("d_cats") or [] 
            # some events use "dcats" and some use "d_cats" as the key for the list of disciplines/categories, so we check for both

            # 2nd level of the JSON is the discipline/category (dcat), which contains information about the specific discipline/category and a list of category rounds
            for dcat in dcats:
                dcat_base = {
                    **event_base,
                    "dcat_id": dcat.get("dcat_id"),
                    "dcat_name": dcat.get("dcat_name"),
                    "discipline_kind": dcat.get("discipline_kind"),
                    "category_id": dcat.get("category_id"),
                    "category_name": dcat.get("category_name"),
                    "dcat_status": dcat.get("status"),
                    "dcat_ranking_as_of": dcat.get("ranking_as_of"),
                    "full_results_url": dcat.get("full_results_url"),
                }
            # 3rd level of the JSON is the category round, which contains information about the specific round of the discipline/category and a list of stages or routes
                for category_round in dcat.get("category_rounds", []):
                    round_base = {
                        **dcat_base,
                        "category_round_id": category_round.get("category_round_id"),
                        "round_kind": category_round.get("kind"),
                        "round_name": category_round.get("name"),
                        "round_status": category_round.get("status"),
                        "round_result_url": category_round.get("result_url"),
                        "format_identifier": category_round.get("format_identifier"),
                        "format": category_round.get("format"),
                    }

                    combined_stages = category_round.get("combined_stages") or []
                    # some category rounds have a "combined_stages" key which contains a list of stages that are combined together, 
                    # while others just have a "routes" key with the routes directly under the category round.

            # 4th level of the JSON is either the stage (if there are combined stages) or the route (if there are no combined stages).
                    if combined_stages:
                        for stage in combined_stages:
                            stage_base = {
                                **round_base,
                                "stage_id": stage.get("id"),
                                "stage_kind": stage.get("kind"),
                                "stage_results_url": stage.get("results"),
                            }

                            for route in stage.get("routes", []):
                                rows.append(
                                    {
                                        **stage_base,
                                        "route_id": route.get("id"),
                                        "route_name": route.get("name"),
                                        "route_startlist_url": route.get("startlist"),
                                        "route_results_url": route.get("ranking"),
                                    }
                                )
                    else:
                        for route in category_round.get("routes", []):
                            rows.append(
                                {
                                    **round_base,
                                    "stage_id": None,
                                    "stage_kind": None,
                                    "stage_results_url": None,
                                    "route_id": route.get("id"),
                                    "route_name": route.get("name"),
                                    "route_startlist_url": route.get("startlist"),
                                    "route_results_url": route.get("ranking"),
                                }
                            )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    flat_df = pd.DataFrame(rows)
    flat_df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Flattened CSV saved to: {output_csv}")
    print(f"Flattened rows: {len(flat_df)}")



# This is where the script starts execution. When you run this script, it will first call the function to scrape the event URLs and save the raw JSONL,
#  and then it will call the function to flatten the JSONL into a CSV file.
if __name__ == "__main__": # this line just means "if we run this script directly (instead of importing it as a module), then execute the following code"
    scrape_event_urls_to_jsonl(headless=False, delay_seconds=0.5)
    flatten_jsonl_to_csv()