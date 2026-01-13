from spotapi import Public
import json

def find_key(obj, target_key, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            if k == target_key:
                print(f"Found {target_key} at: {new_path} = {v}")
            find_key(v, target_key, new_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            find_key(item, target_key, new_path)

def debug_info():
    playlist_id = "37i9dQZF1DWXRqgorJj26U"
    try:
        iterator = Public.playlist_info(playlist_id)
        first_chunk = next(iterator)
        
        print("Searching for 'totalCount'...")
        find_key(first_chunk, "totalCount")
        
        print("Searching for 'items'...")
        find_key(first_chunk, "items")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_info()
