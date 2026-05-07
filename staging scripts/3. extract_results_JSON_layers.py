### YOU WILL NEED TO DELETE YOUR CHECKPOINT FILE (all_results_checkpoint.json) TO RERUN THIS SCRIPT FROM THE START, 
### OR ADJUST THE CHECKPOINT TO RESUME FROM A SPECIFIC URL LAYER/INDEX.

# you may need to run 'playwright install' in the terminal to get the browsers

from pathlib import Path
import json
import time
import pandas as pd
from playwright.sync_api import sync_playwright

#### THE AIM OF THIS SCRIPT IS TO:
# 1) Read the all_events_flat.csv file, which contains the URLs for each event's results page.
# 2) For each URL, we will extract the JSON data that contains the detailed results for that event.
# 3) We will save each event's results as a separate JSONL file, where each line corresponds to a single result entry
# 4) Convert the JSONL files into a single CSV file for easier analysis and integration with other datasets.

## REMINDER: This script is designed to be run in batches, one URL layer at a time, 
# to avoid overwhelming the server and to allow for easier debugging and error handling.
# You can adjust the batch size and delay between requests in the `scrape_results_urls_to_jsonl` function below. 
# After each batch, the script saves a checkpoint so you can resume from where it left off if needed.

# import the list of event URLs from the CSV file
BASE = Path("new_raw_data") # the folder path
EVENT_RESULTS_CSV = BASE / "all_events_flat.csv" # the CSV file we created in the previous step that contains the list of event URLs to scrape
RESULTS_RAW_JSONL = BASE / "all_results_raw.jsonl" # the output JSONL file where we will save the raw JSON data for each event (one JSON object per line)
RESULTS_FLAT_CSV = BASE / "all_results_meta_flat.csv" # the output CSV file where we will save the flattened data
RESULTS_RANKINGS_FLAT_CSV = BASE / "all_rankings_flat.csv" # flattened athlete ranking/ascent level data
RESULTS_CHECKPOINT_FILE = BASE / "all_results_checkpoint.json"

# Choose which year(s) to extract from EVENTS_CSV:
# - Set to None to include all years in events_data.csv.
# - Set to [2024] for one year, or [2022, 2023, 2024] for multiple years.
RESULTS_YEARS_TO_EXTRACT = None #[2024]

# Dictionary: Year to seasonID mapping
seasons = {
    # Initial sequence
    1990: 3, 1991: 4, 1992: 5, 1993: 6, 1994: 7,
    1995: 8, 1996: 9, 1997: 10, 1998: 11, 1999: 12,
    2000: 13, 2001: 14, 2002: 15, 2003: 16, 2004: 17,
    2005: 18, 2006: 19, 2007: 20, 2008: 21, 2009: 22,
    2010: 23, 2011: 24, 2012: 25, 2013: 26, 2014: 27,
    2015: 28, 2016: 29, 2017: 30, 2018: 31, 2019: 32,
    # 2020 outlier
    2020: 2, 
    # Resuming the sequence (2021 is 33)
    2021: 33, 2022: 34, 2023: 35, 2024: 36, 2025: 37, 2026: 38,
    # 2027 is omitted currently because it has no data yet
    2028: 39
    }

# These are the layers of result URLs we want to extract from the events CSV. 
# Each layer corresponds to a different type of result page on the IFSC website
# They have different URL patterns and JSON structures. 
# By organizing them into layers, we can handle each type separately and ensure we capture all relevant data.
URL_COLUMNS = [
    "full_results_url" 
    # the full results page for each event contains the full nested data (below) for each event, round and route
    #,"round_result_url"
    #,"stage_results_url"
    #,"route_startlist_url"
    #,"route_results_url"
]

# This function reads each URL layer separately and returns a de-duplicated list per layer.
    # the function returns a dictionary where the keys are the layer names (from URL_COLUMNS) and the values are lists of URLs for that layer
def load_results_urls_by_layer() -> dict[str, list[str]]: 
    # Read the CSV file and select only the columns we need (season_id and the URL columns). 
    event_results_urls = pd.read_csv(EVENT_RESULTS_CSV, usecols=["season_id", *URL_COLUMNS])
# If RESULTS_YEARS_TO_EXTRACT is set, we filter the data to include only the rows that match the specified years.
    if RESULTS_YEARS_TO_EXTRACT:
        years = [int(y) for y in RESULTS_YEARS_TO_EXTRACT]
        season_ids = [seasons[y] for y in years if y in seasons]
        missing_years = [y for y in years if y not in seasons]
# If there are any years specified in RESULTS_YEARS_TO_EXTRACT that do not have a corresponding season_id in the seasons mapping, we log a warning message.
        if missing_years:
            print(f"Warning: no season_id mapping found for year(s): {missing_years}")
# If we have valid season_ids, we filter the event_results_urls to include only the rows where the season_id is in our list of season_ids.
        if season_ids:
            event_results_urls = event_results_urls[event_results_urls["season_id"].isin(season_ids)]
        else:
            print("Warning: no valid season_id values derived from RESULTS_YEARS_TO_EXTRACT; no rows selected.")
            event_results_urls = event_results_urls.iloc[0:0]
# For each URL column (layer), we drop any missing values, convert to string, strip whitespace, and then create a list of unique URLs for that layer.
    urls_by_layer: dict[str, list[str]] = {}
    for col in URL_COLUMNS:
        layer_urls = event_results_urls[col].dropna().astype(str).str.strip()
        urls_by_layer[col] = [url for url in pd.unique(layer_urls) if url]
    return urls_by_layer

# These two functions handle checkpointing, which allows us to save our progress after each batch of URLs is processed.
def load_checkpoint() -> dict[str, int]:
    if not RESULTS_CHECKPOINT_FILE.exists():
        return {"stage_index": 0, "url_index": 0}

    with RESULTS_CHECKPOINT_FILE.open("r", encoding="utf-8") as f:
        state = json.load(f)
# we return the stage_index and url_index from the checkpoint file, which tells us which URL layer 
# and which URL within that layer we should start from when we resume the script.
    return {
        "stage_index": int(state.get("stage_index", 0)),
        "url_index": int(state.get("url_index", 0)),
    }

# this function saves the current stage_index and url_index to the checkpoint file, 
# so that if we need to stop and restart the script, we can pick up from where we left off instead of starting over.
def save_checkpoint(stage_index: int, url_index: int) -> None:
    checkpoint = {"stage_index": stage_index, "url_index": url_index}
    with RESULTS_CHECKPOINT_FILE.open("w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)

# This function uses Playwright to automate a browser, visit each result URL, and capture the JSON data returned by the website's API.
# By default, it runs in headless mode (no browser window), but you can set headless=False for debugging or if the site blocks headless browsers.
# It also includes a time delay between requests to avoid overwhelming the server and to mimic more human-like browsing behavior.
def scrape_results_urls_to_jsonl(
    headless: bool = False,
    delay_seconds: float = 0.5,
    batch_size: int = 500, # number of URLs to process before saving a checkpoint; adjust based on memory constraints and desired checkpoint frequency
    stages_per_run: int = 1, # number of URL layers to process in one run; set to 1 to do one layer at a time, or higher to do multiple layers
) -> None:
    urls_by_layer = load_results_urls_by_layer()
    RESULTS_RAW_JSONL.parent.mkdir(parents=True, exist_ok=True) # make sure the output directory exists
    state = load_checkpoint() # load the checkpoint to see where we left off in the last run, so we can resume from there instead of starting over

    stage_start = max(0, state["stage_index"]) # determine the starting stage based on the checkpoint
    stage_end = min(stage_start + max(stages_per_run, 1), len(URL_COLUMNS)) # determine the ending stage for this run, start stage + stages_per_run or the total number of stages, whichever is smaller
# if the starting stage is greater than or equal to the number of URL layers, 
# this means we have already completed all stages in previous runs, so we log a message and exit the function.
    if stage_start >= len(URL_COLUMNS):
        print("All stages are already complete. Delete checkpoint to rerun from start.")
        return

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

        # Open in append mode so reruns/resumes do not wipe prior successful data.
        with RESULTS_RAW_JSONL.open("a", encoding="utf-8") as jsonl_file:
            # these loops go through each URL layer (stage) and then through each URL in that layer, making the API request and saving the JSON response to the JSONL file.
            for stage_index in range(stage_start, stage_end):
                layer_name = URL_COLUMNS[stage_index]
                results_urls = urls_by_layer.get(layer_name, [])
                start_url_index = state["url_index"] if stage_index == stage_start else 0

                print(f"\nStage {stage_index + 1}/{len(URL_COLUMNS)}: {layer_name}")
                print(f"URLs in stage: {len(results_urls)} | starting at index: {start_url_index}")
                # we process the URLs in batches, so we can save our progress after each batch and avoid losing too much work if something goes wrong.
                for batch_start in range(start_url_index, len(results_urls), batch_size):
                    batch_end = min(batch_start + batch_size, len(results_urls))
                    print(f"  Batch {batch_start}:{batch_end}")
                # these loops go through each URL in the current batch, make the API request to get the JSON data, and then save that data to the JSONL file.
                    for i in range(batch_start, batch_end):
                        results_url = results_urls[i]
                        print(f"[{i + 1}/{len(results_urls)}] Fetching {results_url}")

                        try:
                            # Use captured headers in case API access depends on dynamic auth context.
                            json_data = page.evaluate(
                                """async ({ url, headers }) => {
                                    const response = await fetch(url, { headers });
                                    return await response.json();
                                }""",
                                {"url": results_url, "headers": api_headers},
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

                        json_data["source_event_url"] = results_url # add the source URL to the JSON data, so we know which event it came from when we process it later
                        json_data["source_url_layer"] = layer_name
                        jsonl_file.write(json.dumps(json_data, ensure_ascii=False) + "\n") # write the JSON data to the JSONL file, one line per event
                        success_count += 1

                        if delay_seconds > 0:
                            time.sleep(delay_seconds) # add a delay between requests to avoid overwhelming the server and to mimic more human-like browsing behavior

                    # Save progress after each batch so reruns continue from the next URL.
                    save_checkpoint(stage_index=stage_index, url_index=batch_end)

                # Move to next stage and reset URL index for that stage.
                save_checkpoint(stage_index=stage_index + 1, url_index=0)

        # Close the browser once the loop is finished
        browser.close()

    print("\nFinished.")
    print(f"Saved JSONL to: {RESULTS_RAW_JSONL}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")

# This function reads the raw JSONL file we created in the previous step, and flattens the nested JSON structure into a single CSV file.
def flatten_results_jsonl_to_csv(input_jsonl: Path = RESULTS_RAW_JSONL, output_csv: Path = RESULTS_FLAT_CSV) -> None:
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
                results_payload = json.loads(line) # parse the JSON data for this event. If it fails, log the error and skip to the next line
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSONL line {line_number}: {exc}")
                continue

            # 1st level of the JSON is the event payload itself.
            # In test_results_raw.jsonl this top-level object carries event + dcat metadata directly,
            # and category_rounds appears directly at the root (not nested under "dcats" or "d_cats").
            event_base = {
                "source_event_url": results_payload.get("source_event_url"),
                "source_url_layer": results_payload.get("source_url_layer"),
                "event_name": results_payload.get("event"),
                "dcat_name": results_payload.get("dcat"),
                "dcat_status": results_payload.get("status"),
                "dcat_status_as_of": results_payload.get("status_as_of"),
                "dcat_ranking_as_of": results_payload.get("ranking_as_of"),
                "cutoff_rank": results_payload.get("cutoff_rank"),
            }

            # Keep backward compatibility with older payloads where category rounds are nested under dcats/d_cats.
            dcats = results_payload.get("dcats") or results_payload.get("d_cats")
            if dcats:
                category_round_groups = [
                    (
                        {
                            **event_base,
                            "dcat_id": dcat.get("dcat_id"),
                            "dcat_name": dcat.get("dcat_name") or event_base.get("dcat_name"),
                            "discipline_kind": dcat.get("discipline_kind"),
                            "category_id": dcat.get("category_id"),
                            "category_name": dcat.get("category_name"),
                            "dcat_status": dcat.get("status") or event_base.get("dcat_status"),
                            "dcat_ranking_as_of": dcat.get("ranking_as_of") or event_base.get("dcat_ranking_as_of"),
                            "full_results_url": dcat.get("full_results_url"),
                        },
                        dcat.get("category_rounds", []),
                    )
                    for dcat in dcats
                ]
            else:
                category_round_groups = [(event_base, results_payload.get("category_rounds", []))]

            # 2nd level of the JSON is the category round, which contains information about the specific round
            # of the discipline/category and a list of stages or routes.
            for dcat_base, category_rounds in category_round_groups:
                for category_round in category_rounds:
                    round_base = {
                        **dcat_base,
                        "category_round_id": category_round.get("category_round_id"),
                        "round_kind": category_round.get("kind"),
                        "round_name": category_round.get("name"),
                        "round_category": category_round.get("category"),
                        "round_status": category_round.get("status"),
                        "round_status_as_of": category_round.get("status_as_of"),
                        "round_result_url": category_round.get("result_url"),
                        "format_identifier": category_round.get("format_identifier"),
                        "format": category_round.get("format"),
                        "league_round_id": (category_round.get("round") or {}).get("league_round_id"),
                    }

                    combined_stages = category_round.get("combined_stages") or []
                    # some category rounds have a "combined_stages" key which contains a list of stages that are combined together,
                    # while others just have a "routes" key with the routes directly under the category round.

                    # 3rd level of the JSON is either the stage (if there are combined stages) or the route (if there are no combined stages).
                    # there are 3 loops here to handle the different possible structures of the JSON, depending on whether combined stages are present or not.
                    if combined_stages:
                        for stage in combined_stages:
                            stage_base = {
                                **round_base,
                                "stage_id": stage.get("id"),
                                "stage_name": stage.get("stage_name"),
                                "stage_kind": stage.get("kind"),
                                "stage_status": stage.get("status"),
                                "stage_status_as_of": stage.get("status_as_of"),
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
                                    "stage_name": None,
                                    "stage_kind": None,
                                    "stage_status": None,
                                    "stage_status_as_of": None,
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

# This function is similar to the previous one, but goes beyond the meta data into the JSON structure 
# to extract detailed information about athlete rankings, rounds, stages, and ascents.
def flatten_rankings_jsonl_to_csv(
    input_jsonl: Path = RESULTS_RAW_JSONL,
    output_csv: Path = RESULTS_RANKINGS_FLAT_CSV,
) -> None:
    if not input_jsonl.exists():
        print(f"JSONL file not found: {input_jsonl}")
        return

    rows = [] # this will hold the flattened athlete ranking rows (including round/stage/ascent detail)

    with input_jsonl.open("r", encoding="utf-8") as f:
        # These loops go through ranking-focused layers from test_results_raw.jsonl:
        # event payload -> ranking list (athletes) -> rounds -> combined_stages -> ascents.
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                results_payload = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSONL line {line_number}: {exc}")
                continue

            # 1st level: event + discipline/category metadata shared by all athlete rows in this payload.
            event_base = {
                "source_event_url": results_payload.get("source_event_url"),
                "source_url_layer": results_payload.get("source_url_layer"),
                "event_name": results_payload.get("event"),
                "dcat_name": results_payload.get("dcat"),
                "dcat_status": results_payload.get("status"),
                "dcat_status_as_of": results_payload.get("status_as_of"),
                "dcat_ranking_as_of": results_payload.get("ranking_as_of"),
                "cutoff_rank": results_payload.get("cutoff_rank"),
            }

            # 2nd level: ranking list where each item is an athlete result summary.
            for athlete in results_payload.get("ranking") or []:
                athlete_base = {
                    **event_base,
                    "athlete_id": athlete.get("athlete_id"),
                    "squad_id": athlete.get("squad_id"),
                    "athlete_rank": athlete.get("rank"),
                    "athlete_name": athlete.get("name"),
                    "bib_number": athlete.get("bib_number"),
                    "firstname": athlete.get("firstname"),
                    "lastname": athlete.get("lastname"),
                    "country": athlete.get("country"),
                    "organisation_id": athlete.get("organisation_id"),
                    "flag_url": athlete.get("flag_url"),
                }

                # 3rd level: each athlete has round-level entries.
                for athlete_round in athlete.get("rounds") or []:
                    round_base = {
                        **athlete_base,
                        "category_round_id": athlete_round.get("category_round_id"),
                        "round_name": athlete_round.get("round_name"),
                        "round_rank": athlete_round.get("rank"),
                        "round_score": athlete_round.get("score"),
                    }

                    combined_stages = athlete_round.get("combined_stages") or []

                    # 4th level: stage-level entries and their ascents/routes.
                    # there are 3 loops here to handle the different possible structures of the JSON, 
                    # depending on whether combined stages are present or not, and whether ascents are present or not.
                    if combined_stages:
                        for stage in combined_stages:
                            stage_base = {
                                **round_base,
                                "stage_name": stage.get("stage_name"),
                                "stage_score": stage.get("stage_score"),
                                "stage_rank": stage.get("stage_rank"),
                            }

                            ascents = stage.get("ascents") or []
                            if ascents:
                                for ascent in ascents:
                                    rows.append(
                                        {
                                            **stage_base,
                                            "route_id": ascent.get("route_id"),
                                            "route_name": ascent.get("route_name"),
                                            "top": ascent.get("top"),
                                            "top_tries": ascent.get("top_tries"),
                                            "zone": ascent.get("zone"),
                                            "zone_tries": ascent.get("zone_tries"),
                                            "low_zone": ascent.get("low_zone"),
                                            "low_zone_tries": ascent.get("low_zone_tries"),
                                            "points": ascent.get("points"),
                                            "score": ascent.get("score"),
                                            "plus": ascent.get("plus"),
                                            "restarted": ascent.get("restarted"),
                                            "time_ms": ascent.get("time_ms"),
                                            "ascent_status": ascent.get("status"),
                                            "ascent_modified": ascent.get("modified"),
                                        }
                                    )
                            else:
                                rows.append(
                                    {
                                        **stage_base,
                                        "route_id": None,
                                        "route_name": None,
                                        "top": None,
                                        "top_tries": None,
                                        "zone": None,
                                        "zone_tries": None,
                                        "low_zone": None,
                                        "low_zone_tries": None,
                                        "points": None,
                                        "score": None,
                                        "plus": None,
                                        "restarted": None,
                                        "time_ms": None,
                                        "ascent_status": None,
                                        "ascent_modified": None,
                                    }
                                )
                    else:
                        rows.append(
                            {
                                **round_base,
                                "stage_name": None,
                                "stage_score": None,
                                "stage_rank": None,
                                "route_id": None,
                                "route_name": None,
                                "top": None,
                                "top_tries": None,
                                "zone": None,
                                "zone_tries": None,
                                "low_zone": None,
                                "low_zone_tries": None,
                                "points": None,
                                "score": None,
                                "plus": None,
                                "restarted": None,
                                "time_ms": None,
                                "ascent_status": None,
                                "ascent_modified": None,
                            }
                        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    ranking_df = pd.DataFrame(rows)
    ranking_df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"Flattened rankings CSV saved to: {output_csv}")
    print(f"Flattened ranking rows: {len(ranking_df)}")




# This is where the script starts execution. When you run this script, it will first call the function to scrape the event URLs and save the raw JSONL,
#  and then it will call the function to flatten the JSONL into a CSV file.
if __name__ == "__main__": # this line just means "if we run this script directly (instead of importing it as a module), then execute the following code"
    scrape_results_urls_to_jsonl(headless=False, 
                                 delay_seconds=0, # set to 0 for no delay; a small delay can help avoid triggering anti-scraping measures on the website
                                 batch_size=500, # smaller batches can help with error handling and reduce memory usage, but larger batches can be faster
    )
    flatten_results_jsonl_to_csv()
    flatten_rankings_jsonl_to_csv()