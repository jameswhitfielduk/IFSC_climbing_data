# you may need to run 'playwright install' in the terminal to get the browsers

from playwright.sync_api import sync_playwright
import pandas as pd
import time
import json

CUWR_PATH = "https://ifsc.results.info/api/v1/cuwr/"
TARGET_CATEGORY_ID = None  # set to a category id (e.g., 617) to fetch one category only; set to None to fetch all
SAVE_RAW_JSON = True
RAW_JSON_PATH = "new_raw_data/test_CUWR_raw.json"
ranking_categories = {1: "LEAD Men",
                      2: "SPEED Men",
                      3: "BOULDER Men",
                      617: "BOULDER&LEAD Men",
                      5: "LEAD Women",
                      6: "SPEED Women",
                      7: "BOULDER Women",
                      618: "BOULDER&LEAD Women"}

def fetch_ifsc_with_playwright():
    base_url = CUWR_PATH

    raw_payloads = []

    # Start Playwright
    with sync_playwright() as p:
        # Launch Chromium. 
        # If the site still blocks you, change to `headless=False` 
        # so it looks even more like a real human user.
        browser = p.chromium.launch(headless=False)
        
    # Create a persistent context. This acts like a browser profile 
    # and will hold our session cookies automatically.
        context = browser.new_context()
        page = context.new_page()

        print("Visiting homepage to establish session and bypass protections...")
        
        # Store the necessary authentication headers here
        api_headers = {
            "Referer": "https://ifsc.results.info/",
            "Origin": "https://ifsc.results.info"
        }
        
        # This function listens to the website's background traffic
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

        # Attach a traffic interceptor to the page
        page.on("request", intercept_background_requests)
        
        # Load the main website and wait until the network is quiet.
        # This forces the website to run its startup routines and make initial API calls.
        page.goto("https://ifsc.results.info/", wait_until="networkidle")
        
        print(f"   -> Session established. Using headers: {api_headers}")

        categories_to_fetch = ranking_categories
        if TARGET_CATEGORY_ID is not None:
            if TARGET_CATEGORY_ID not in ranking_categories:
                raise ValueError(f"TARGET_CATEGORY_ID {TARGET_CATEGORY_ID} is not in ranking_categories")
            categories_to_fetch = {TARGET_CATEGORY_ID: ranking_categories[TARGET_CATEGORY_ID]}

        for category_id, category in categories_to_fetch.items():
            print(f"Navigating to {category} data (Category ID: {category_id})...")
            endpoint = f"{base_url}/{category_id}"
            
            # Run JavaScript natively inside the webpage context.
            # The browser's native fetch() will automatically include all required auth headers
            # because it thinks the website itself is asking for the data.
            json_data = page.evaluate(f"""async () => {{
                const response = await fetch('{endpoint}');
                return await response.json();
            }}""")
            
            # Check for authorisation errors in the response
            if isinstance(json_data, dict) and json_data.get("message") == "Not Authorized!":
                print(f"  -> Failed: The server still rejected the request for {category}.")
                continue

            # Save one raw JSON payload so you can inspect the exact response structure.
            if SAVE_RAW_JSON:
                with open(RAW_JSON_PATH, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                print(f"  -> Saved raw JSON to {RAW_JSON_PATH}")

            # Keep payloads to flatten after scraping.
            raw_payloads.append(
                {
                    "category_id": category_id,
                    "category_name": category,
                    "payload": json_data,
                }
            )

            # A 1-second delay between requests to avoid rate-limiting
            time.sleep(1)

        # Close the browser once the loop is finished
        browser.close()

    # Flatten payloads using ranking + score_breakdown structure from test_CUWR_raw.json.
    flat_rows = []
    for item in raw_payloads:
        payload = item["payload"]
        payload_base = {
            "ranking_category_id": item["category_id"],
            "ranking_category": item["category_name"],
            "dcat_name": payload.get("dcat_name"),
            "discipline_kind": payload.get("discipline_kind"),
            "ranking_name": payload.get("ranking_name"),
            "ranking_id": payload.get("ranking_id"),
            "ranking_from": payload.get("from"),
            "ranking_to": payload.get("to"),
            "continental_council_ranking_url": payload.get("continental_council_ranking_url"),
        }

        for athlete in payload.get("ranking") or []:
            athlete_base = {
                **payload_base,
                "athlete_id": athlete.get("athlete_id"),
                "athlete_name": athlete.get("name"),
                "firstname": athlete.get("firstname"),
                "lastname": athlete.get("lastname"),
                "federation_id": athlete.get("federation_id"),
                "country": athlete.get("country"),
                "athlete_rank": athlete.get("rank"),
                "athlete_score": athlete.get("score"),
                "photo_url": athlete.get("photo_url"),
            }

            score_breakdown = athlete.get("score_breakdown") or []
            if score_breakdown:
                for breakdown in score_breakdown:
                    flat_rows.append(
                        {
                            **athlete_base,
                            "event_id": breakdown.get("event_id"),
                            "event_discipline_id": breakdown.get("discipline_id"),
                            "event_discipline_kind": breakdown.get("discipline_kind"),
                            "event_rank": breakdown.get("rank"),
                            "event_name": breakdown.get("event_name"),
                            "event_start_date": breakdown.get("event_start_date"),
                            "event_end_date": breakdown.get("event_end_date"),
                            "field_factor": breakdown.get("field_factor"),
                            "gained_pts": breakdown.get("gained_pts"),
                            "original_pts": breakdown.get("original_pts"),
                            "included": breakdown.get("included"),
                        }
                    )
            else:
                flat_rows.append(
                    {
                        **athlete_base,
                        "event_id": None,
                        "event_discipline_id": None,
                        "event_discipline_kind": None,
                        "event_rank": None,
                        "event_name": None,
                        "event_start_date": None,
                        "event_end_date": None,
                        "field_factor": None,
                        "gained_pts": None,
                        "original_pts": None,
                        "included": None,
                    }
                )

    rankings_df = pd.DataFrame(flat_rows)

    # Flatten the events payload to a separate table (one row per event).
    event_rows = []
    for item in raw_payloads:
        payload = item["payload"]
        payload_base = {
            "ranking_category_id": item["category_id"],
            "ranking_category": item["category_name"],
            "dcat_name": payload.get("dcat_name"),
            "discipline_kind": payload.get("discipline_kind"),
            "ranking_name": payload.get("ranking_name"),
            "ranking_id": payload.get("ranking_id"),
            "ranking_from": payload.get("from"),
            "ranking_to": payload.get("to"),
        }

        for event in payload.get("events") or []:
            event_rows.append(
                {
                    **payload_base,
                    "event_id": event.get("id"),
                    "event_name": event.get("name"),
                    "location": event.get("location"),
                    "event_discipline_id": event.get("discipline_id"),
                    "event_discipline_kind": event.get("discipline_kind"),
                    "starts_at": event.get("starts_at"),
                    "ends_at": event.get("ends_at"),
                    "depreciation_factor": event.get("depreciation_factor"),
                    "field_factor": event.get("field_factor"),
                }
            )

    events_df = pd.DataFrame(event_rows)
    return rankings_df, events_df

# Run the function to get the flattened DataFrame from the JSON structure.
rankings_df, events_df = fetch_ifsc_with_playwright()

# Export flattened ranking rows to CSV
rankings_df.to_csv("new_raw_data/CUWR_rankings.csv", index=False)
print(f"CUWR rankings data saved to: new_raw_data/CUWR_rankings.csv")

# Export flattened event rows to CSV
events_df.to_csv("new_raw_data/CUWR_events.csv", index=False)
print(f"CUWR events data saved to: new_raw_data/CUWR_events.csv")