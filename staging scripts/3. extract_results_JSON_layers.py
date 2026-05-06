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

# import the list of event URLs from the CSV file
BASE = Path("new_raw_data") # the folder path
EVENT_RESULTS_CSV = BASE / "all_events_flat.csv" # the CSV file we created in the previous step that contains the list of event URLs to scrape
RAW_JSONL = BASE / "all_results_raw.jsonl" # the output JSONL file where we will save the raw JSON data for each event (one JSON object per line)
FLAT_CSV = BASE / "all_results_flat.csv" # the output CSV file where we will save the flattened data
CHECKPOINT_FILE = BASE / "all_results_checkpoint.json"

URL_COLUMNS = [
    "full_results_url",
    "round_result_url",
    "stage_results_url",
    "route_startlist_url",
    "route_results_url",
]

# This function reads each URL layer separately and returns a de-duplicated list per layer.
def load_results_urls_by_layer() -> dict[str, list[str]]:
    event_results_urls = pd.read_csv(EVENT_RESULTS_CSV, usecols=URL_COLUMNS)
    urls_by_layer: dict[str, list[str]] = {}
    for col in URL_COLUMNS:
        layer_urls = event_results_urls[col].dropna().astype(str).str.strip()
        urls_by_layer[col] = [url for url in pd.unique(layer_urls) if url]
    return urls_by_layer


def load_checkpoint() -> dict[str, int]:
    if not CHECKPOINT_FILE.exists():
        return {"stage_index": 0, "url_index": 0}

    with CHECKPOINT_FILE.open("r", encoding="utf-8") as f:
        state = json.load(f)

    return {
        "stage_index": int(state.get("stage_index", 0)),
        "url_index": int(state.get("url_index", 0)),
    }


def save_checkpoint(stage_index: int, url_index: int) -> None:
    checkpoint = {"stage_index": stage_index, "url_index": url_index}
    with CHECKPOINT_FILE.open("w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)

# This function uses Playwright to automate a browser, visit each result URL, and capture the JSON data returned by the website's API.
 # by default, it runs in headless mode (no browser window), but you can set headless=False for debugging or if the site blocks headless browsers.
 # It also includes a time delay between requests to avoid overwhelming the server and to mimic more human-like browsing behavior.
def scrape_results_urls_to_jsonl(
    headless: bool = False,
    delay_seconds: float = 0.5,
    batch_size: int = 500,
    stages_per_run: int = 1,
) -> None:
    urls_by_layer = load_results_urls_by_layer()
    RAW_JSONL.parent.mkdir(parents=True, exist_ok=True)
    state = load_checkpoint()

    stage_start = max(0, state["stage_index"])
    stage_end = min(stage_start + max(stages_per_run, 1), len(URL_COLUMNS))

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
        with RAW_JSONL.open("a", encoding="utf-8") as jsonl_file:
            for stage_index in range(stage_start, stage_end):
                layer_name = URL_COLUMNS[stage_index]
                results_urls = urls_by_layer.get(layer_name, [])
                start_url_index = state["url_index"] if stage_index == stage_start else 0

                print(f"\nStage {stage_index + 1}/{len(URL_COLUMNS)}: {layer_name}")
                print(f"URLs in stage: {len(results_urls)} | starting at index: {start_url_index}")

                for batch_start in range(start_url_index, len(results_urls), batch_size):
                    batch_end = min(batch_start + batch_size, len(results_urls))
                    print(f"  Batch {batch_start}:{batch_end}")

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
    print(f"Saved JSONL to: {RAW_JSONL}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")

# This is where the script starts execution. When you run this script, it will first call the function to scrape the event URLs and save the raw JSONL,
#  and then it will call the function to flatten the JSONL into a CSV file.
if __name__ == "__main__": # this line just means "if we run this script directly (instead of importing it as a module), then execute the following code"
    scrape_results_urls_to_jsonl(headless=False, delay_seconds=0.5, batch_size=500, stages_per_run=1)
   # flatten_jsonl_to_csv()