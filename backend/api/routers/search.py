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
        
        # Handle v2 wrapper
        if isinstance(result, dict) and 'data' in result and 'version' in result:
            result = result['data']
        
        # The /album/ endpoint returns items directly (not under 'tracks' key)
        # Each item is wrapped: {"item": {...track...}, "type": "track"}
        raw_items = result.get('items', []) if isinstance(result, dict) else result
        
        tracks = []
        for item in raw_items:
            # Unwrap if nested in 'item' key
            track = item.get('item', item) if isinstance(item, dict) else item
            if isinstance(track, dict) and 'id' in track:
                tracks.append(track)
        
        log_info(f"Found {len(tracks)} tracks in album")
        
        # Convert to same format as search results
        return {
            "items": [
                TrackSearchResult(
                    id=track['id'],
                    title=track.get('title', 'Unknown'),
                    artist=track.get('artist', {}).get('name', 'Unknown') if isinstance(track.get('artist'), dict) else (track.get('artists', [{}])[0].get('name', 'Unknown') if track.get('artists') else 'Unknown'),
                    album=track.get('album', {}).get('title') if isinstance(track.get('album'), dict) else None,
                    duration=track.get('duration'),
                    cover=track.get('album', {}).get('cover') if isinstance(track.get('album'), dict) else None,
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
        
        if not artist_info:
            return {"info": None, "top_tracks": [], "albums": []}
        
        top_tracks = []
        albums = []
        
        # Helper to check if something looks like an album
        def is_album_like(obj):
            return isinstance(obj, dict) and 'id' in obj and 'title' in obj and ('numberOfTracks' in obj or 'cover' in obj)
        
        # Helper to check if something looks like a track
        def is_track_like(obj):
            return isinstance(obj, dict) and 'id' in obj and 'title' in obj and 'duration' in obj
        
        # Extract albums - deeply nested: albums.rows[].modules[].pagedList.items[]
        albums_data = artist_info.get('albums', {})
        if isinstance(albums_data, dict):
            # Navigate: rows -> modules -> pagedList -> items
            rows = albums_data.get('rows', [])
            for row in rows:
                if isinstance(row, dict):
                    modules = row.get('modules', [])
                    for module in modules:
                        if isinstance(module, dict):
                            paged_list = module.get('pagedList', {})
                            if isinstance(paged_list, dict):
                                items = paged_list.get('items', [])
                                for item in items:
                                    album = item.get('item', item) if isinstance(item, dict) else item
                                    if is_album_like(album):
                                        albums.append({
                                            'id': album['id'],
                                            'title': album['title'],
                                            'year': album.get('releaseDate', '').split('-')[0] if album.get('releaseDate') else '',
                                            'cover': album.get('cover'),
                                            'numberOfTracks': album.get('numberOfTracks')
                                        })
            
            # Fallback: try direct items or rows if modules structure wasn't found
            if not albums:
                album_list = albums_data.get('items', [])
                for item in album_list:
                    album = item.get('item', item) if isinstance(item, dict) else item
                    if is_album_like(album):
                        albums.append({
                            'id': album['id'],
                            'title': album['title'],
                            'year': album.get('releaseDate', '').split('-')[0] if album.get('releaseDate') else '',
                            'cover': album.get('cover'),
                            'numberOfTracks': album.get('numberOfTracks')
                        })
        
        # Extract tracks - they might be a direct list or in 'tracks.items'
        tracks_data = artist_info.get('tracks', [])
        if isinstance(tracks_data, list):
            track_list = tracks_data
        elif isinstance(tracks_data, dict):
            track_list = tracks_data.get('items', tracks_data.get('rows', []))
        else:
            track_list = []
        
        for item in track_list[:10]:  # Limit to top 10
            track = item.get('item', item) if isinstance(item, dict) else item
            if is_track_like(track):
                top_tracks.append({
                    'id': track['id'],
                    'title': track['title'],
                    'album': track.get('album', {}).get('title') if isinstance(track.get('album'), dict) else None,
                    'duration': track['duration'],
                    'quality': track.get('audioQuality', 'LOSSLESS'),
                    'cover': track.get('album', {}).get('cover') if isinstance(track.get('album'), dict) else None
                })
        
        # Sort albums by year (newest first)
        def get_album_timestamp(album):
            year = album.get('year', '')
            if not year: return 0
            try: return int(year)
            except: return 0
        
        albums.sort(key=get_album_timestamp, reverse=True)
        
        log_info(f"Found {len(albums)} albums, {len(top_tracks)} top tracks for artist {artist_id}")
        
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
