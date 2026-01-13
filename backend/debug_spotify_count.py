from spotapi import Public
import json

def get_count(chain, *keys):
    curr = chain
    for k in keys:
        if isinstance(curr, dict) and k in curr:
            curr = curr[k]
        else:
            return None
    return curr

def debug_count():
    playlist_id = "37i9dQZF1DWXRqgorJj26U"
    try:
        iterator = Public.playlist_info(playlist_id)
        first_chunk = next(iterator)
        
        # Try paths
        paths = [
            ['playlist', 'content', 'totalCount'],
            ['playlist', 'tracks', 'totalCount'],
            ['playlist', 'totalCount'],
            ['totalCount'],
            ['playlist', 'content', 'pagingInfo', 'totalCount'] # unlikely
        ]
        
        for p in paths:
            val = get_count(first_chunk, *p)
            if val is not None:
                print(f"FOUND totalCount at path {'.'.join(p)}: {val}")
                return

        print("totalCount NOT FOUND in standard paths.")
        # Print root keys
        print("Root keys:", first_chunk.keys())
        if 'playlist' in first_chunk:
             print("Playlist keys:", first_chunk['playlist'].keys())
             if 'content' in first_chunk['playlist']:
                 print("Playlist.content keys:", first_chunk['playlist']['content'].keys())

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_count()
