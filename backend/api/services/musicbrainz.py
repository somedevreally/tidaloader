"""
MusicBrainz Metadata Service

Provides Picard-like metadata lookup using the MusicBrainz API.
Fetches comprehensive metadata including:
- MusicBrainz IDs (track, album, artist, release group)
- Accurate release dates
- Genre information
- Recording details
- Label information
"""

import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from api.utils.logging import log_info, log_warning, log_success


MB_API_BASE = "https://musicbrainz.org/ws/2"
MB_USER_AGENT = "Tidaloader/1.0 (https://github.com/RayZ3R0/tidaloader)"
MB_RATE_LIMIT_DELAY = 1.0  


_mb_cache: Dict[str, Dict] = {}


async def lookup_musicbrainz_metadata(
    title: str,
    artist: str,
    album: Optional[str] = None,
    duration_ms: Optional[int] = None,
    isrc: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Look up track metadata from MusicBrainz.
    
    Tries multiple strategies:
    1. ISRC lookup (most accurate if available)
    2. Recording search by title + artist
    3. Release search with track matching
    
    Returns a dict with MusicBrainz metadata or None if not found.
    """
    cache_key = f"{artist}:{title}:{album or ''}"
    if cache_key in _mb_cache:
        log_info(f"[MusicBrainz] Cache hit for {artist} - {title}")
        return _mb_cache[cache_key]
    
    log_info(f"[MusicBrainz] Looking up: {artist} - {title}")
    
    result = None
    
    
    if isrc:
        result = await _lookup_by_isrc(isrc)
        if result:
            log_success(f"[MusicBrainz] Found via ISRC: {isrc}")
    
    
    if not result:
        result = await _search_recording(title, artist, album, duration_ms)
        if result:
            log_success(f"[MusicBrainz] Found via recording search")
    
    
    if not result and album:
        result = await _search_release_with_track(title, artist, album)
        if result:
            log_success(f"[MusicBrainz] Found via release search")
    
    if result:
        _mb_cache[cache_key] = result
        return result
    
    log_warning(f"[MusicBrainz] No match found for {artist} - {title}")
    return None


async def _make_mb_request(endpoint: str, params: Dict[str, str]) -> Optional[Dict]:
    """Make a request to the MusicBrainz API with rate limiting."""
    params['fmt'] = 'json'
    
    headers = {
        'User-Agent': MB_USER_AGENT,
        'Accept': 'application/json'
    }
    
    url = f"{MB_API_BASE}/{endpoint}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 503:
                    
                    log_warning("[MusicBrainz] Rate limited, waiting...")
                    await asyncio.sleep(MB_RATE_LIMIT_DELAY * 2)
                    return None
                else:
                    return None
    except Exception as e:
        log_warning(f"[MusicBrainz] Request failed: {e}")
        return None
    finally:
        
        await asyncio.sleep(MB_RATE_LIMIT_DELAY)


async def _lookup_by_isrc(isrc: str) -> Optional[Dict[str, Any]]:
    """Look up a recording by ISRC code."""
    data = await _make_mb_request("isrc/" + isrc, {
        'inc': 'recordings+releases+artists+release-groups+genres+tags'
    })
    
    if not data or 'recordings' not in data:
        return None
    
    recordings = data.get('recordings', [])
    if not recordings:
        return None
    
    
    recording = recordings[0]
    return _extract_metadata_from_recording(recording)


async def _search_recording(
    title: str,
    artist: str,
    album: Optional[str] = None,
    duration_ms: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Search for a recording by title and artist."""
    
    query_parts = [
        f'recording:"{_escape_lucene(title)}"',
        f'artist:"{_escape_lucene(artist)}"'
    ]
    
    if album:
        query_parts.append(f'release:"{_escape_lucene(album)}"')
    
    query = ' AND '.join(query_parts)
    
    data = await _make_mb_request("recording", {
        'query': query,
        'limit': '10'
    })
    
    if not data or 'recordings' not in data:
        return None
    
    recordings = data.get('recordings', [])
    if not recordings:
        return None
    
    
    best_recording = _find_best_recording_match(recordings, title, artist, duration_ms)
    if not best_recording:
        return None
    
    
    recording_id = best_recording.get('id')
    if not recording_id:
        return _extract_metadata_from_recording(best_recording)
    
    detailed = await _make_mb_request(f"recording/{recording_id}", {
        'inc': 'releases+artists+release-groups+genres+tags+isrcs'
    })
    
    if detailed:
        return _extract_metadata_from_recording(detailed)
    
    return _extract_metadata_from_recording(best_recording)


async def _search_release_with_track(
    title: str,
    artist: str,
    album: str
) -> Optional[Dict[str, Any]]:
    """Search for a release and match the track within it."""
    query = f'release:"{_escape_lucene(album)}" AND artist:"{_escape_lucene(artist)}"'
    
    data = await _make_mb_request("release", {
        'query': query,
        'limit': '5'
    })
    
    if not data or 'releases' not in data:
        return None
    
    releases = data.get('releases', [])
    if not releases:
        return None
    
    
    for release in releases[:3]:
        release_id = release.get('id')
        if not release_id:
            continue
        
        detailed = await _make_mb_request(f"release/{release_id}", {
            'inc': 'recordings+artists+release-groups+genres+tags+labels'
        })
        
        if not detailed:
            continue
        
        
        media = detailed.get('media', [])
        for medium in media:
            tracks = medium.get('tracks', [])
            for track in tracks:
                recording = track.get('recording', {})
                track_title = recording.get('title', '')
                
                if _titles_match(track_title, title):
                    
                    result = _extract_metadata_from_recording(recording)
                    
                    result.update(_extract_release_metadata(detailed))
                    result['track_number'] = track.get('position')
                    result['disc_number'] = medium.get('position', 1)
                    return result
    
    return None


def _extract_metadata_from_recording(recording: Dict) -> Dict[str, Any]:
    """Extract standardized metadata from a MusicBrainz recording."""
    result = {
        'musicbrainz_trackid': recording.get('id'),
        'musicbrainz_recordingid': recording.get('id'),
    }
    
    
    if recording.get('title'):
        result['mb_title'] = recording['title']
    
    
    artist_credit = recording.get('artist-credit', [])
    if artist_credit:
        artists = []
        artist_ids = []
        for credit in artist_credit:
            artist = credit.get('artist', {})
            if artist.get('name'):
                artists.append(artist['name'])
            if artist.get('id'):
                artist_ids.append(artist['id'])
        
        if artists:
            result['mb_artist'] = artists[0]  
            result['mb_artists'] = artists
        if artist_ids:
            result['musicbrainz_artistid'] = artist_ids[0]
            result['musicbrainz_artistids'] = artist_ids
    
    
    if recording.get('length'):
        result['mb_duration'] = recording['length']  
    
    
    genres = []
    for genre in recording.get('genres', []):
        genres.append(genre.get('name'))
    for tag in recording.get('tags', []):
        if tag.get('count', 0) >= 1:
            genres.append(tag.get('name'))
    if genres:
        result['mb_genres'] = list(set(genres))[:5]  
        result['genre'] = genres[0] if genres else None
    
    
    isrcs = recording.get('isrcs', [])
    if isrcs:
        result['isrc'] = isrcs[0]
    
    
    releases = recording.get('releases', [])
    if releases:
        release = releases[0]
        result.update(_extract_release_metadata(release))
    
    return result


def _extract_release_metadata(release: Dict) -> Dict[str, Any]:
    """Extract metadata from a MusicBrainz release."""
    result = {}
    
    
    if release.get('id'):
        result['musicbrainz_albumid'] = release['id']
    
    
    if release.get('title'):
        result['mb_album'] = release['title']
    
    
    date = release.get('date') or release.get('release-date')
    if date:
        result['mb_date'] = date
        
        if len(date) >= 4:
            result['mb_year'] = date[:4]
    
    
    release_group = release.get('release-group', {})
    if release_group:
        if release_group.get('id'):
            result['musicbrainz_releasegroupid'] = release_group['id']
        
        
        primary_type = release_group.get('primary-type')
        if primary_type:
            result['mb_releasetype'] = primary_type.lower()
    
    
    artist_credit = release.get('artist-credit', [])
    if artist_credit:
        album_artists = []
        for credit in artist_credit:
            artist = credit.get('artist', {})
            if artist.get('name'):
                album_artists.append(artist['name'])
        if album_artists:
            result['mb_album_artist'] = album_artists[0]
            result['musicbrainz_albumartistid'] = artist_credit[0].get('artist', {}).get('id')
    
    
    if release.get('country'):
        result['mb_country'] = release['country']
    
    
    label_info = release.get('label-info', [])
    if label_info:
        labels = []
        for li in label_info:
            label = li.get('label', {})
            if label.get('name'):
                labels.append(label['name'])
        if labels:
            result['mb_label'] = labels[0]
            result['mb_labels'] = labels
    
    
    if release.get('barcode'):
        result['mb_barcode'] = release['barcode']
    
    
    media = release.get('media', [])
    if media:
        total_tracks = sum(m.get('track-count', 0) for m in media)
        if total_tracks:
            result['mb_total_tracks'] = total_tracks
        result['mb_total_discs'] = len(media)
    
    return result


def _find_best_recording_match(
    recordings: List[Dict],
    title: str,
    artist: str,
    duration_ms: Optional[int] = None
) -> Optional[Dict]:
    """Find the best matching recording from a list."""
    scored = []
    
    for recording in recordings:
        score = 0
        
        
        rec_title = recording.get('title', '')
        if _titles_match(rec_title, title):
            score += 50
        elif title.lower() in rec_title.lower() or rec_title.lower() in title.lower():
            score += 30
        
        
        artist_credit = recording.get('artist-credit', [])
        for credit in artist_credit:
            rec_artist = credit.get('artist', {}).get('name', '')
            if rec_artist.lower() == artist.lower():
                score += 40
            elif artist.lower() in rec_artist.lower():
                score += 20
        
        
        if duration_ms and recording.get('length'):
            diff = abs(duration_ms - recording['length'])
            if diff < 5000:
                score += 20
            elif diff < 10000:
                score += 10
        
        
        if recording.get('releases'):
            score += 10
        
        
        rec_score = recording.get('score', 0)
        if rec_score:
            score += min(rec_score // 10, 10)
        
        if score > 0:
            scored.append((score, recording))
    
    if not scored:
        return None
    
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _titles_match(title1: str, title2: str) -> bool:
    """Check if two titles match (case-insensitive, ignoring extra info)."""
    def normalize(s: str) -> str:
        
        import re
        s = re.sub(r'\s*[\(\[][^\)\]]*(?:remaster|remix|edit|version|mix|live|acoustic|demo|radio|explicit|clean).*?[\)\]]', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\s*-\s*(?:remaster|remix|edit|version|single).*$', '', s, flags=re.IGNORECASE)
        return s.lower().strip()
    
    return normalize(title1) == normalize(title2)


def _escape_lucene(s: str) -> str:
    """Escape special characters for Lucene query."""
    special = r'+-&|!(){}[]^"~*?:\/'
    for char in special:
        s = s.replace(char, f'\\{char}')
    return s


async def enhance_metadata_with_musicbrainz(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance existing metadata with MusicBrainz data.
    
    This is the main entry point for integrating MusicBrainz into the download flow.
    It takes the existing metadata and enriches it with MusicBrainz data where available.
    """
    title = metadata.get('title')
    artist = metadata.get('artist')
    album = metadata.get('album')
    duration = metadata.get('duration')
    
    if not title or not artist:
        log_warning("[MusicBrainz] Missing title or artist, skipping lookup")
        return metadata
    
    
    duration_ms = None
    if duration:
        if duration < 10000:  
            duration_ms = duration * 1000
        else:
            duration_ms = duration
    
    
    mb_data = await lookup_musicbrainz_metadata(
        title=title,
        artist=artist,
        album=album,
        duration_ms=duration_ms
    )
    
    if not mb_data:
        return metadata
    
    
    
    enhanced = metadata.copy()
    
    
    if mb_data.get('musicbrainz_trackid'):
        enhanced['musicbrainz_trackid'] = mb_data['musicbrainz_trackid']
    if mb_data.get('musicbrainz_albumid'):
        enhanced['musicbrainz_albumid'] = mb_data['musicbrainz_albumid']
    if mb_data.get('musicbrainz_artistid'):
        enhanced['musicbrainz_artistid'] = mb_data['musicbrainz_artistid']
    if mb_data.get('musicbrainz_albumartistid'):
        enhanced['musicbrainz_albumartistid'] = mb_data['musicbrainz_albumartistid']
    if mb_data.get('musicbrainz_releasegroupid'):
        enhanced['musicbrainz_releasegroupid'] = mb_data['musicbrainz_releasegroupid']
    
    
    if not enhanced.get('date') and mb_data.get('mb_date'):
        enhanced['date'] = mb_data['mb_date']
    
    
    if not enhanced.get('genre') and mb_data.get('genre'):
        enhanced['genre'] = mb_data['genre']
    
    
    if not enhanced.get('isrc') and mb_data.get('isrc'):
        enhanced['isrc'] = mb_data['isrc']
    
    
    if not enhanced.get('album_artist') and mb_data.get('mb_album_artist'):
        enhanced['album_artist'] = mb_data['mb_album_artist']
    
    
    if mb_data.get('mb_label'):
        enhanced['label'] = mb_data['mb_label']
    
    
    if not enhanced.get('total_tracks') and mb_data.get('mb_total_tracks'):
        enhanced['total_tracks'] = mb_data['mb_total_tracks']
    if not enhanced.get('total_discs') and mb_data.get('mb_total_discs'):
        enhanced['total_discs'] = mb_data['mb_total_discs']
    
    
    added_fields = []
    if enhanced.get('musicbrainz_trackid'):
        added_fields.append('MB Track ID')
    if enhanced.get('musicbrainz_albumid'):
        added_fields.append('MB Album ID')
    if enhanced.get('genre') and not metadata.get('genre'):
        added_fields.append(f'Genre: {enhanced["genre"]}')
    if enhanced.get('date') and not metadata.get('date'):
        added_fields.append(f'Date: {enhanced["date"]}')
    
    if added_fields:
        log_success(f"[MusicBrainz] Enhanced: {', '.join(added_fields)}")
    
    return enhanced
