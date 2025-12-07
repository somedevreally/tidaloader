from typing import List, Optional
from api.utils.logging import log_info, log_warning, log_error

def extract_items(result, key: str) -> List:
    # log_info(f"extract_items called for key: {key}")
    # log_info(f"Result type: {type(result)}")
    
    if not result:
        log_warning("extract_items received empty result")
        return []
    
    # Debug extraction for troubleshooting
    if isinstance(result, dict):
        if key in result:
             pass
             # log_info(f"Key '{key}' found in result struct")
        else:
             log_warning(f"Key '{key}' NOT found in result struct. Keys: {list(result.keys())}")

    
    if isinstance(result, list):
        if len(result) > 0 and isinstance(result[0], dict):
            first_elem = result[0]
            if key in first_elem:
                nested = first_elem[key]
                if isinstance(nested, dict) and 'items' in nested:
                    return nested['items']
                elif isinstance(nested, list):
                    return nested
        return result
    
    if isinstance(result, dict):
        if key in result and isinstance(result[key], dict):
            return result[key].get('items', [])
        
        if 'items' in result:
            return result['items']
    
    return []

def extract_track_data(track_response) -> List:
    if not track_response:
        return []
    
    if isinstance(track_response, list):
        for item in track_response:
            if isinstance(item, dict) and 'items' in item:
                return item['items']
        return []
    
    if isinstance(track_response, dict):
        return track_response.get('items', [])
    
    return []

def extract_stream_url(track_data) -> Optional[str]:
    if isinstance(track_data, list):
        entries = track_data
    else:
        entries = [track_data]
    
    for entry in entries:
        if isinstance(entry, dict) and 'OriginalTrackUrl' in entry:
            return entry['OriginalTrackUrl']
    
    for entry in entries:
        if isinstance(entry, dict) and 'manifest' in entry:
            manifest = entry['manifest']
            try:
                import base64
                decoded = base64.b64decode(manifest).decode('utf-8')
                
                try:
                    import json
                    manifest_json = json.loads(decoded)
                    if 'urls' in manifest_json and manifest_json['urls']:
                        return manifest_json['urls'][0]
                except json.JSONDecodeError:
                    pass
                
                import re
                url_match = re.search(r'https?://[^\s"]+', decoded)
                if url_match:
                    return url_match.group(0)
            except Exception as e:
                log_error(f"Failed to decode manifest: {e}")
    
    return None
