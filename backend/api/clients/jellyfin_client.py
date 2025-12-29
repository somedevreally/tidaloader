import logging
import requests
from typing import Optional, Dict, List, Any
from urllib.parse import urljoin
from api.settings import settings

logger = logging.getLogger(__name__)

class JellyfinClient:
    def __init__(self):
        self.session = requests.Session()
        
    def _get_headers(self) -> Dict[str, str]:
        if not settings.jellyfin_api_key:
            return {}
        
        return {
            "X-Emby-Token": settings.jellyfin_api_key,
            "Content-Type": "application/json",
            # Standard Jellyfin/Emby client headers
            "X-Emby-Authorization": f'MediaBrowser Client="Tidaloader", Device="Server", DeviceId="TidaloaderServer", Version="1.0.0", Token="{settings.jellyfin_api_key}"'
        }

    def _get_base_url(self) -> Optional[str]:
        if not settings.jellyfin_url:
            return None
        return settings.jellyfin_url.rstrip("/")

    def get_system_info(self, url: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Test connection and authentication.
        Returns system info dict or raises Exception.
        """
        # Determine actual URL and Key
        target_url = url.rstrip("/") if url else self._get_base_url()
        target_key = api_key if api_key else settings.jellyfin_api_key

        if not target_url or not target_key:
            raise ValueError("Jellyfin URL or API Key not configured")

        endpoint = f"{target_url}/System/Info"
        
        # Prepare headers for this request specifically if overrides are used
        headers = {
            "X-Emby-Token": target_key,
            "Content-Type": "application/json",
            "X-Emby-Authorization": f'MediaBrowser Client="Tidaloader", Device="Server", DeviceId="TidaloaderServer", Version="1.0.0", Token="{target_key}"'
        }

        try:
            response = self.session.get(endpoint, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Jellyfin connection failed: {e}")
            raise Exception(f"Failed to connect to Jellyfin: {str(e)}")

    def get_users(self) -> List[Dict[str, Any]]:
        """
        Get all users from Jellyfin.
        """
        base_url = self._get_base_url()
        if not base_url:
            logger.error("get_users: No base_url configured")
            return []

        url = f"{base_url}/Users"
        try:
            # According to Jellyfin API, /Users gets all users if admin
            response = self.session.get(url, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            users = response.json()
            return users
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            return []

    def get_user_image(self, user_id: str) -> Optional[bytes]:
        """
        Get user profile image.
        """
        base_url = self._get_base_url()
        if not base_url:
            return None
            
        # Jellyfin API: /Users/{Id}/Images/Primary
        url = f"{base_url}/Users/{user_id}/Images/Primary"
        
        try:
            response = self.session.get(url, headers=self._get_headers(), timeout=10)
            if response.status_code == 200:
                return response.content
            return None
        except Exception:
            return None

    def find_playlist_id(self, name: str) -> Optional[str]:
        """
        Search for a playlist by name.
        """
        base_url = self._get_base_url()
        if not base_url:
            return None

        url = f"{base_url}/Items"
        params = {
            "Recursive": "true",
            "IncludeItemTypes": "Playlist",
            "SearchTerm": name,
            "Limit": 1
        }
        
        try:
            response = self.session.get(url, params=params, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("TotalRecordCount", 0) > 0 and data.get("Items"):
                # Double check exact name match to be safe? 
                # Or trust search. Let's return first match.
                return data["Items"][0]["Id"]
            return None
        except Exception as e:
            logger.error(f"Failed to find playlist {name}: {e}")
            return None

    def upload_image(self, item_id: str, image_data: bytes, image_type: str = "Primary") -> bool:
        """
        Upload an image (cover) for an item.
        """
        base_url = self._get_base_url()
        if not base_url:
            return False

        # Jellyfin API: POST /Items/{Id}/Images/{Type}
        # Content-Type should be image/* (e.g. image/jpeg) but requests handles it if we pass data
        # Actually jellyfin expects binary body.
        
        url = f"{base_url}/Items/{item_id}/Images/{image_type}"
        headers = self._get_headers()
        headers["Content-Type"] = "image/jpeg" # Assuming JPG for now as we save .jpg
        
        try:
            response = self.session.post(url, data=image_data, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info(f"Successfully uploaded image for item {item_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload image for {item_id}: {e}")
            return False

jellyfin_client = JellyfinClient()
