# you may need to run 'playwright install' in the terminal to get the browsers

from playwright.sync_api import sync_playwright
import pandas as pd
import time
import json # to allow export of whole json responses for debugging if needed

test_event_url = "https://ifsc.results.info/api/v1/events/1385" # Olympic Qualifier Series Budapest 2024

# import the list of event URLs from the CSV file
events_data_urls = pd.read_csv("new_raw_data/events_data.csv", usecols=["event_url"])
print(events_data_urls.head())

def scrape_event_urls(url):
    extracted_data = []

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

        # Save full JSON response for the configured test URL.
        test_json_data = page.evaluate(f"""async () => {{
            const response = await fetch('{test_event_url}');
            return await response.json();
        }}""")
        test_output_file = "new_raw_data/test_url_response.json"
        with open(test_output_file, "w", encoding="utf-8") as f:
            json.dump(test_json_data, f, indent=4)
        print(f"  -> Saved full JSON for test URL to {test_output_file}")

        # Debug-only early exit: skip looping through all event URLs.
        browser.close()
        return pd.DataFrame()

        # Now use Playwright's API context. This uses the browser's current 
        # session (cookies) + the authentication headers.
        api_request = context.request

        for i, event_url in events_data_urls.iterrows():
            event_url = event_url["event_url"]
            print(f"Navigating to {event_url}...")
            endpoint = event_url
            
            # Run JavaScript natively inside the webpage context.
            # The browser's native fetch() will automatically include all required auth headers
            # because it thinks the website itself is asking for the data.
            json_data = page.evaluate(f"""async () => {{
                const response = await fetch('{endpoint}');
                return await response.json();
            }}""")
            
            # Check for authorisation errors in the response
            if isinstance(json_data, dict) and json_data.get("message") == "Not Authorized!":
                print(f"  -> Failed: The server still rejected the request for {event_url}.")
                continue
              
            # Parse out the fields
            events = json_data.get("events", []) 
            
            if not events:
                print(f"  -> No events found for {event_url}.")

            for event in events:
                        extracted_data.append({
                            "year": year,
                            "event_id": event.get("event_id", None),
                            "event": event.get("event", "Unknown"),
                            "cup_id": event.get("cup_id", None),
                            "cup_name": event.get("cup_name", "Unknown"),
                            "location": event.get("location", "Unknown"),
                            "country": event.get("country", "Unknown"),
                            "local_start_date": event.get("local_start_date", None),
                            "local_end_date": event.get("local_end_date", None),
                            "event_url": f"https://ifsc.results.info/{event.get('url', f'events/{event.get("id")}')}"
                        })

            # A 1-second delay between requests to avoid rate-limiting
            time.sleep(1)

        # Close the browser once the loop is finished
        browser.close()

    # Convert to Pandas DataFrame
    df = pd.DataFrame(extracted_data)

    # Keep numeric IDs as whole numbers and date columns in ISO format.
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["event_id"] = pd.to_numeric(df["event_id"], errors="coerce").astype("Int64")
    df["cup_id"] = pd.to_numeric(df["cup_id"], errors="coerce").astype("Int64")
    df["local_start_date"] = pd.to_datetime(df["local_start_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["local_end_date"] = pd.to_datetime(df["local_end_date"], errors="coerce").dt.strftime("%Y-%m-%d")

    return df

# Run the function
ifsc_events_df = scrape_event_urls(test_event_url)

# Export extracted events to CSV
ifsc_events_df.to_csv("new_raw_data/event_by_event_data.csv", index=False)

# Display the results
print("\n--- Final Pandas DataFrame ---")
print(ifsc_events_df.head(10))