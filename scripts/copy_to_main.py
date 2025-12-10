# scripts/copy_to_main.py
import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def copy_stage_to_main():
    # Approach: delete main and insert stage snapshot.
    # If you want to keep existing main IDs or do upsert, change accordingly.
    print("Deleting main table rows...")
    sb.table("satellites_main").delete().neq("id", 0).execute()

    print("Getting stage data...")
    res = sb.table("satellites_stage").select("*").execute()
    if res.error:
        raise Exception(res.error)
    data = res.data or []
    # remove 'id' so auto identity will assign
    to_insert = []
    for r in data:
        r.pop("id", None)
        to_insert.append(r)
    if to_insert:
        print(f"Inserting {len(to_insert)} rows into main...")
        sb.table("satellites_main").insert(to_insert).execute()
    print("Copy complete.")

if __name__ == "__main__":
    copy_stage_to_main()
