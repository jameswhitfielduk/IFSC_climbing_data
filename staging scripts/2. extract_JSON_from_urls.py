# you may need to run 'playwright install' in the terminal to get the browsers

from pathlib import Path
import json
import time
import pandas as pd
from playwright.sync_api import sync_playwright


# import the list of event URLs from the CSV file
BASE = Path("new_raw_data")
EVENTS_CSV = BASE / "events_data.csv"
RAW_JSONL = BASE / "all_events_raw.jsonl"
FLAT_CSV = BASE / "all_events_flat.csv"


def load_event_urls() -> list[str]:
    events_data_urls = pd.read_csv(EVENTS_CSV, usecols=["event_url"])
    urls = events_data_urls["event_url"].dropna().astype(str).str.strip()
    urls = [url for url in urls.unique() if url]
    return urls


def scrape_event_urls_to_jsonl(headless: bool = False, delay_seconds: float = 0.5) -> None:
    event_urls = load_event_urls()
    RAW_JSONL.parent.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0

    with sync_playwright() as p:
        # Launch Chromium. 
        # If the site still blocks you, change to `headless=False` 
        # so it looks even more like a real human user.
        browser = p.chromium.launch(headless=headless)
        
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

        with RAW_JSONL.open("w", encoding="utf-8") as jsonl_file:
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
                    fail_count += 1
                    print(f"  -> Request failed: {exc}")
                    continue

                if isinstance(json_data, dict) and json_data.get("message") == "Not Authorized!":
                    fail_count += 1
                    print("  -> Not Authorized")
                    continue

                if not isinstance(json_data, dict):
                    fail_count += 1
                    print(f"  -> Skipped unexpected payload type: {type(json_data)}")
                    continue

                json_data["source_event_url"] = event_url
                jsonl_file.write(json.dumps(json_data, ensure_ascii=False) + "\n")
                success_count += 1

                if delay_seconds > 0:
                    time.sleep(delay_seconds)

        # Close the browser once the loop is finished
        browser.close()

    print("\nFinished.")
    print(f"Saved JSONL to: {RAW_JSONL}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")


def flatten_jsonl_to_csv(input_jsonl: Path = RAW_JSONL, output_csv: Path = FLAT_CSV) -> None:
    if not input_jsonl.exists():
        print(f"JSONL file not found: {input_jsonl}")
        return

    rows = []

    with input_jsonl.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                event_payload = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSONL line {line_number}: {exc}")
                continue

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


if __name__ == "__main__":
    scrape_event_urls_to_jsonl(headless=False, delay_seconds=0.5)
    flatten_jsonl_to_csv()