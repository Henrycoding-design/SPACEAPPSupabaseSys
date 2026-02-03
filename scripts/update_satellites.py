# scripts/update_satellites.py
import os
import time
import requests
from supabase import create_client
from n2yo_key_manager import key_manager, N2YO_KEYS

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
# N2YO_KEY = os.getenv("N2YO_KEY")  # your N2YO key
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Sample locations: (lat, lon) list. 10 major cities around the world.
LOCATIONS = [
    (40.7128, -74.0060),   # New York City, USA
    (51.5074, -0.1278),    # London, United Kingdom
    (35.6895, 139.6917),   # Tokyo, Japan
    (-33.8688, 151.2093),  # Sydney, Australia
    (48.8566, 2.3522),     # Paris, France
    (1.3521, 103.8198),    # Singapore
    (19.0760, 72.8777),    # Mumbai, India
    (-23.5505, -46.6333),  # São Paulo, Brazil
    (30.0444, 31.2357),    # Cairo, Egypt
    (37.7749, -122.4194),  # San Francisco, USA
]

CATIDS = [
    3,   # Weather
    4,   # NOAA
    6,   # Earth resources
    8,   # Disaster monitoring
    15,  # Iridium
    20,  # GPS Operational
    26,  # Space & Earth Science
    30,  # Military
    50,  # GPS Constellation
    52,  # Starlink
]


def copy_main_to_stage():
    # delete stage, copy from main
    sb.table("satellites_stage").delete().neq("id", 0).execute()
    
    try:
        res = sb.table("satellites_main").select("*").execute()
    except Exception as e:
        raise Exception(f"DB error: {e}")
    
    data = res.data or []
    if data:
        # remove 'id' fields to allow new identity
        for r in data:
            r.pop("id", None)
        sb.table("satellites_stage").insert(data).execute()

def sanity_check_keys():
    for i, key in enumerate(N2YO_KEYS):
        try:
            test_url = f"https://api.n2yo.com/rest/v1/satellite/categories&apiKey={key}"
            r = requests.get(test_url, timeout=20)
            if r.status_code != 200:
                raise Exception(f"HTTP err: {r.status_code}")
        except Exception as e:
            print(f"[WARN] N2YO key {i} failed sanity check: {e}")

def fetch_with_backoff(url_builder, max_retries=8, base_delay=1):
    tried_keys = set()
    for attempt in range(max_retries):
        api_key = key_manager.current()
        url = url_builder(api_key)

        try:
            r = requests.get(url, timeout=50)

            # Key expired / rate limited → rotate + retry immediately
            if r.status_code in (401, 403, 429):
                tried_keys.add(api_key)
                if len(tried_keys) >= len(key_manager.keys):
                    tried_keys.clear()
                    raise Exception("All API Keys exhausted")
                print(f"[N2YO] Key issue ({r.status_code}), rotating key")
                key_manager.rotate()
                continue

            if 400 <= r.status_code < 500:
                r.raise_for_status()

            if r.status_code >= 500:
                raise Exception(f"Server error {r.status_code}")

            try:
                return r.json()
            except ValueError:
                raise Exception("Invalid JSON from N2YO")

        except requests.HTTPError:
            raise
        except Exception as e:
            wait = min(base_delay * (2 ** attempt), 120)
            print(f"Fetch error: {e}. Retry in {wait}s")
            time.sleep(wait)

    raise Exception("Fetch failed after retries")

def validate_tle(norad):
    return fetch_with_backoff(lambda k: f"https://api.n2yo.com/rest/v1/satellite/tle/{norad}&apiKey={k}")

def scan_catid_locations(catid, max_new_per_cat=10):
    new_count = 0
    for lat, lon in LOCATIONS:
        if new_count >= max_new_per_cat:
            break
        
        try:
            payload = fetch_with_backoff(lambda k: f"https://api.n2yo.com/rest/v1/satellite/above/{lat}/{lon}/0/70/{catid}/&apiKey={k}")

            for sat in payload.get("above", []):
                norad = int(sat.get("satid"))
                name = sat.get("satname")
                # check exists in stage
                exists = sb.table("satellites_stage") \
                .select("norad_id") \
                .eq("norad_id", norad) \
                .limit(1) \
                .execute()
                if not exists.data:
                    # insert new
                    sb.table("satellites_stage").insert({
                        "norad_id": norad,
                        "name": name,
                        "catid": catid,
                        "status": True
                    }).execute()
                    new_count += 1
                    if new_count >= max_new_per_cat:
                        break
        except Exception as e:
            print(f"Scan error:{e} for catid {catid} at loc ({lat},{lon})")
    return new_count

def clean_stage(rate_sleep=7):
    # iterate through stage and validate via N2YO TLE or sat query
    res = sb.table("satellites_stage").select("*").execute()
    sats = res.data or []
    for sat in sats:
        norad = sat["norad_id"]
        # call N2YO tle endpoint to verify
        try:
            # Example TLE endpoint from N2YO (replace with correct path)
            payload = validate_tle(norad)
            # consider it valid; update timestamp and ensure status True
            sb.table("satellites_stage").update({
                "status": True,
                "updated_at": "now()"
            }).eq("norad_id", norad).execute()
        except Exception as e:
            # not found or invalid
            sb.table("satellites_stage").update({
                "status": False,
                "updated_at": "now()"
            }).eq("norad_id", norad).execute()
            print("Clean error for", norad, e)

        time.sleep(rate_sleep)

def main():
    print("Checking Keys...")
    sanity_check_keys()

    print("Copy main -> stage")
    copy_main_to_stage()

    print("Scanning categories...")
    for cat in CATIDS:
        nnew = scan_catid_locations(cat, max_new_per_cat=10)
        print(f"cat {cat} new: {nnew}")

    print("Cleaning stage (validating sats)...")
    clean_stage(rate_sleep=7)

    # done, now call approval_check.py externally from GH Action to create approval and wait.
    print("Update finished: stage is ready for approval.")

if __name__ == "__main__":
    main()
