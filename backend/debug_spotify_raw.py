from spotapi.public import client_pool
from spotapi.song import Song
import json

def debug_search():
    client = client_pool.get()
    try:
        song_api = Song(client=client)
        # Search for a standard user playlist
        print("Searching for 'Rock Classics'...")
        response = song_api.query_songs("Rock Classics", limit=5)
        
        if "data" in response and "searchV2" in response["data"]:
            data = response["data"]["searchV2"]
            if "playlists" in data and "items" in data["playlists"]:
                items = data["playlists"]["items"]
                if items:
                    # Dump the first item
                    print(json.dumps(items[0], indent=2))
                else:
                    print("No playlists found in items.")
            else:
                 print("No playlists section in searchV2")
        else:
            print("Invalid response structure")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client_pool.put(client)

if __name__ == "__main__":
    debug_search()
