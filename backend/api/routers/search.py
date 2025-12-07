from fastapi import APIRouter, Depends, HTTPException
from api.auth import require_auth
from api.clients import tidal_client
from api.utils.logging import log_info, log_error
from api.utils.extraction import extract_items
from api.models import TrackSearchResult, TroiTrackResponse

router = APIRouter()

@router.get("/api/search/tracks")
async def search_tracks(q: str, username: str = Depends(require_auth)):
    try:
        log_info(f"Search tracks request for query: {q}")
        result = tidal_client.search_tracks(q)
        
        if not result:
            return {"items": []}
        
        tracks = extract_items(result, 'tracks')
        log_info(f"Found {len(tracks)} tracks")
        
        return {
            "items": [
                TrackSearchResult(
                    id=track['id'],
                    title=track['title'],
                    artist=track.get('artist', {}).get('name', 'Unknown'),
                    album=track.get('album', {}).get('title'),
                    duration=track.get('duration'),
                    cover=track.get('album', {}).get('cover'),
                    quality=track.get('audioQuality')
                )
                for track in tracks
            ]
        }
    except Exception as e:
        log_error(f"Error searching tracks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/search/albums")
async def search_albums(q: str, username: str = Depends(require_auth)):
    try:
        log_info(f"Searching albums: {q}")
        result = tidal_client.search_albums(q)
        
        if not result:
            log_info("No ALBUM results from API")
            return {"items": []}
        
        albums = extract_items(result, 'albums')
        log_info(f"Found {len(albums)} albums")
        
        return {"items": albums}
    except Exception as e:
        log_error(f"Error searching albums: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/search/artists")
async def search_artists(q: str, username: str = Depends(require_auth)):
    try:
        log_info(f"Searching for artist: {q}")
        result = tidal_client.search_artists(q)
        
        if not result:
            log_info("No results from API")
            return {"items": []}
        
        log_info(f"API response type: {type(result)}")
        
        artists = extract_items(result, 'artists')
        
        log_info(f"Found {len(artists)} artists")
        if artists:
            log_info(f"First artist: {artists[0].get('name', 'Unknown')} (ID: {artists[0].get('id')})")
        
        return {"items": artists}
    except Exception as e:
        log_error(f"Error searching artists: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/album/{album_id}/tracks")
async def get_album_tracks(album_id: int, username: str = Depends(require_auth)):
    try:
        log_info(f"Getting tracks for album: {album_id}")
        result = tidal_client.get_album_tracks(album_id)
        
        if not result:
            return {"items": []}
            
        tracks = extract_items(result, 'tracks')
        if not tracks and isinstance(result, list):
             tracks = result
             
        log_info(f"Found {len(tracks)} tracks in album")
        
        # Convert to same format as search results
        return {
            "items": [
                TrackSearchResult(
                    id=track['id'],
                    title=track['title'],
                    artist=track.get('artist', {}).get('name', 'Unknown'),
                    album=track.get('album', {}).get('title'),
                    duration=track.get('duration'),
                    cover=track.get('album', {}).get('cover'),
                    quality=track.get('audioQuality')
                )
                for track in tracks
            ]
        }
    except Exception as e:
        log_error(f"Error getting album tracks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/artist/{artist_id}")
async def get_artist(artist_id: int, username: str = Depends(require_auth)):
    try:
        log_info(f"Getting info for artist: {artist_id}")
        
        artist_info = tidal_client.get_artist(artist_id)
        
        # Helper functions for this endpoint
        def is_track_like(obj):
            return isinstance(obj, dict) and 'id' in obj and 'title' in obj and 'duration' in obj

        def is_album_like(obj):
             return isinstance(obj, dict) and 'id' in obj and 'title' in obj and 'numberOfTracks' in obj

        def is_artist_like(obj):
             return isinstance(obj, dict) and 'id' in obj and 'name' in obj and 'type' in obj

        top_tracks = []
        albums = []
        
        def scan_value(value, depth=0):
            if depth > 3: return
            
            if isinstance(value, dict):
                # Try to identify objects
                if is_track_like(value):
                    if len(top_tracks) < 10 and value.get('type') != 'VIDEO':
                        exists = any(t['id'] == value['id'] for t in top_tracks)
                        if not exists:
                             top_tracks.append({
                                 'id': value['id'],
                                 'title': value['title'],
                                 'album': value.get('album', {}).get('title'),
                                 'duration': value['duration'],
                                 'quality': value.get('audioQuality', 'LOSSLESS'),
                                 'cover': value.get('album', {}).get('cover')
                             })
                
                elif is_album_like(value):
                    exists = any(a['id'] == value['id'] for a in albums)
                    if not exists:
                         albums.append({
                             'id': value['id'],
                             'title': value['title'],
                             'year': value.get('releaseDate', '').split('-')[0] if value.get('releaseDate') else '',
                             'cover': value.get('cover')
                         })

                # Recursively scan dictionary values
                for k, v in value.items():
                    scan_value(v, depth + 1)
                    
            elif isinstance(value, list):
                # Recursively scan list items
                for item in value:
                    scan_value(item, depth + 1)

        # Scan the artist info
        scan_value(artist_info)
        
        # Manual fetch if scan failed
        if not albums:
            log_info("Fetching albums explicitly")
            albums_result = tidal_client.get_artist_albums(artist_id) if hasattr(tidal_client, 'get_artist_albums') else None
            # Extract albums if result exists (implementation dependent on client)
            
        def get_album_timestamp(album):
            year = album.get('year', '')
            if not year: return 0
            try: return int(year)
            except: return 0
            
        albums.sort(key=get_album_timestamp, reverse=True)
            
        return {
            "info": artist_info,
            "top_tracks": top_tracks,
            "albums": albums
        }
        
    except Exception as e:
        log_error(f"Error getting artist info: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
