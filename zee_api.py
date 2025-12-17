import os
import re
import json
import time
import logging
import subprocess
from queue import Queue
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import asyncio
import aiohttp
from helpers.config import PROXY_URL, PROXIES, USE_PROXY

DEVICE_PATH = "samsung_sm-g935f.wvd"  # Path to Widevine device file

PROXIES = {
    'http': PROXY_URL,
    'https': PROXY_URL
} if USE_PROXY else None

# Set up logging with a single handler and consistent format
logging.basicConfig(
    level=logging.CRITICAL,
    format='%(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def load_or_generate_tokens() -> Tuple[str, str]:
    """Load tokens from file or fetch new ones if needed"""
    tokens_file = "data/zee_tokens.json"
    os.makedirs("data", exist_ok=True)
    
    try:
        current_time = time.time()
        refresh_needed = True    
        refresh_token = "34aba640c84f85eb544f44bccaace4a34eca0074c82d3a658dd5140ca014888b"
        device_id = "aa90b69d-eab9-471d-888b-a441f433c7dd"
        access_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwbGF0Zm9ybV9jb2RlIjoiV2ViQCQhdDM4NzEyIiwiaXNzdWVkQXQiOiIyMDI1LTA4LTI2VDExOjQ3OjI5LjQ5OFoiLCJwcm9kdWN0X2NvZGUiOiJ6ZWU1QDk3NSIsInR0bCI6ODY0MDAwMDAsImlhdCI6MTc1NjIwODg0OX0.lvCY2c6x_B3UXB-nXts0-d401MgAvBRuJC0HXI4PoQs"        

        if os.path.exists(tokens_file):
            with open(tokens_file, 'r') as f:
                data = json.load(f)
                
                if 'timestamp' in data and current_time - data.get('timestamp', 0) < 86400:
                    logger.info("Using cached tokens (less than 1 day old)")
                    refresh_needed = False
                    return data['bearer_token'], access_token
                
                if 'refresh_token' in data:
                    refresh_token = data['refresh_token']
        
        if refresh_needed:
            logger.info("Fetching new bearer token from Zee5 auth API")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
                "Accept": "application/json", 
                "Accept-Language": "en-US,en;q=0.5",
                "Content-Type": "application/json",
                "X-Z5-Guest-Token": device_id,
                "device_id": device_id,
                "esk": "OWEzOTExYWItNzE4Zi00YTQyLTkzNzQtNzAzMDNiYWZjMTdmX19nQlFhWkxpTmRHTjlVc0NLWmFsb2doejl0OVN0V0xTRF9fMTc0NjQ0NzcwNzg1MQ==",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors", 
                "Sec-Fetch-Site": "same-site",
                "Priority": "u=4"
            }
            
            connector = aiohttp.TCPConnector(ssl=False)
            proxy = PROXY_URL if USE_PROXY else None
            
            try:
                async with aiohttp.ClientSession(connector=connector) as session:
                    url = f"https://auth.zee5.com/v1/user/renew?refresh_token={refresh_token}"
                    async with session.post(url, headers=headers, proxy=proxy) as response:
                        if response.status == 200:
                            token_data = await response.json()
                            
                            with open(tokens_file, 'w') as f:
                                data = {
                                    "bearer_token": token_data.get("access_token", ""),
                                    "access_token": access_token,
                                    "refresh_token": token_data.get("refresh_token", refresh_token),
                                    "expires_in": token_data.get("expires_in", 345600),
                                    "timestamp": current_time,
                                    "device_id": device_id
                                }
                                json.dump(data, f, indent=4)
                                
                            logger.info(f"New bearer token fetched and saved to {tokens_file}")
                            return data["bearer_token"], access_token
                        else:
                            logger.error(f"Failed to fetch bearer token: {response.status}")
                            
                            if os.path.exists(tokens_file):
                                with open(tokens_file, 'r') as f:
                                    data = json.load(f)
                                    logger.warning("Using existing bearer token as fallback")
                                    return data['bearer_token'], access_token
            except Exception as e:
                logger.error(f"Error fetching bearer token: {str(e)}")
                
                if os.path.exists(tokens_file):
                    with open(tokens_file, 'r') as f:
                        data = json.load(f)
                        logger.warning("Using existing bearer token as fallback after error")
                        return data['bearer_token'], access_token
        
        logger.warning("Using placeholder bearer token as last resort")
        placeholder_data = {
            "bearer_token": "eyJraWQiOiJkZjViZjBjOC02YTAxLTQ0MWEtOGY2MS0yMDllMjE2MGU4MTUiLCJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJBMTFDRTJDNy0zRDQ4LTREM0UtQjM5MS0wMDYzNTA3RDhCREEiLCJkZXZpY2VfaWQiOiI4YmU5MjQ4MS1mMGVlLTQ0M2MtOTEzNi0xMTdmNDE4YjZlMGQiLCJhbXIiOlsiZGVsZWdhdGlvbiJdLCJ0YXJnZXRlZF9pZCI6dHJ1ZSwiaXNzIjoiaHR0cHM6Ly91c2VyYXBpLnplZTUuY29tIiwidmVyc2lvbiI6MTAsImNsaWVudF9pZCI6InJlZnJlc2hfdG9rZW4iLCJhdWQiOlsidXNlcmFwaSIsInN1YnNjcmlwdGlvbmFwaSIsInByb2ZpbGVhcGkiLCJnYW1lLXBsYXkiXSwidXNlcl90eXBlIjoiUmVnaXN0ZXJlZCIsIm5iZiI6MTc1MjA2OTM2OSwidXNlcl9pZCI6ImExMWNlMmM3LTNkNDgtNGQzZS1iMzkxLTAwNjM1MDdkOGJkYSIsInNjb3BlIjpbInVzZXJhcGkiLCJzdWJzY3JpcHRpb25hcGkiLCJwcm9maWxlYXBpIl0sInNlc3Npb25fdHlwZSI6IkdFTkVSQUwiLCJleHAiOjE3NTI0MTQ5NjksImlhdCI6MTc1MjA2OTM2OSwianRpIjoiNGRhNjZkY2UtY2Y0OC00MmEwLWIxNzItY2E0Yzg3YjI1MTZlIn0.FHfN8hfSrGL-P-YvYDDgPSaLCf3l_NVcarw5O1gO3BAFp15JzPb4j1s72o2aaC8HNOKgMMJnsChE5QSZ4EaC5phMOdwT42LB-0hgfjf-Pt6-glRy47YnFJ_vyqplCAyP1QFdK8uIcmexqe8l6zYZZELXNf8Q_JGGBiHMUT8mkE8J8vNMAc6IUs6jMj2w16Plr-Wc4ycwmELJ9lmq2uY5S9aUtuwvyc-3_qKPPQHIWqvmR1BtHCm4sM30iyM1btmzjByY4Ar5PMIjaKrTzJmf3lGsKZhX7lKKPeQMF1c1IC0EL5pQXmXQ3cJxWVVBNaEN7m-TAFDn8fYkeo07_-Bnhg",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "timestamp": current_time,
            "device_id": device_id
        }
        
        with open(tokens_file, 'w') as f:
            json.dump(placeholder_data, f, indent=4)
            
        return placeholder_data['bearer_token'], access_token
    except Exception as e:
        logger.error(f"Error in token handling: {str(e)}")
        # Return placeholder bearer token as last resort
        return "eyJraWQiOiJkZjViZjBjOC02YTAxLTQ0MWEtOGY2MS0yMDllMjE2MGU4MTUiLCJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJBMTFDRTJDNy0zRDQ4LTREM0UtQjM5MS0wMDYzNTA3RDhCREEiLCJkZXZpY2VfaWQiOiI4YmU5MjQ4MS1mMGVlLTQ0M2MtOTEzNi0xMTdmNDE4YjZlMGQiLCJhbXIiOlsiZGVsZWdhdGlvbiJdLCJ0YXJnZXRlZF9pZCI6dHJ1ZSwiaXNzIjoiaHR0cHM6Ly91c2VyYXBpLnplZTUuY29tIiwidmVyc2lvbiI6MTAsImNsaWVudF9pZCI6InJlZnJlc2hfdG9rZW4iLCJhdWQiOlsidXNlcmFwaSIsInN1YnNjcmlwdGlvbmFwaSIsInByb2ZpbGVhcGkiLCJnYW1lLXBsYXkiXSwidXNlcl90eXBlIjoiUmVnaXN0ZXJlZCIsIm5iZiI6MTc1MjA2OTM2OSwidXNlcl9pZCI6ImExMWNlMmM3LTNkNDgtNGQzZS1iMzkxLTAwNjM1MDdkOGJkYSIsInNjb3BlIjpbInVzZXJhcGkiLCJzdWJzY3JpcHRpb25hcGkiLCJwcm9maWxlYXBpIl0sInNlc3Npb25fdHlwZSI6IkdFTkVSQUwiLCJleHAiOjE3NTI0MTQ5NjksImlhdCI6MTc1MjA2OTM2OSwianRpIjoiNGRhNjZkY2UtY2Y0OC00MmEwLWIxNzItY2E0Yzg3YjI1MTZlIn0.FHfN8hfSrGL-P-YvYDDgPSaLCf3l_NVcarw5O1gO3BAFp15JzPb4j1s72o2aaC8HNOKgMMJnsChE5QSZ4EaC5phMOdwT42LB-0hgfjf-Pt6-glRy47YnFJ_vyqplCAyP1QFdK8uIcmexqe8l6zYZZELXNf8Q_JGGBiHMUT8mkE8J8vNMAc6IUs6jMj2w16Plr-Wc4ycwmELJ9lmq2uY5S9aUtuwvyc-3_qKPPQHIWqvmR1BtHCm4sM30iyM1btmzjByY4Ar5PMIjaKrTzJmf3lGsKZhX7lKKPeQMF1c1IC0EL5pQXmXQ3cJxWVVBNaEN7m-TAFDn8fYkeo07_-Bnhg", access_token
def extract_content_id(url: str) -> str:
    """Extract content ID from ZEE5 URL"""
    # Pattern for web series (show level)
    series_pattern = r'web-series/details/[^/]+/([^/\s]+)$'
    # Pattern for web series episodes
    web_series_pattern = r'web-series/details/[^/]+/[^/]+/[^/]+/([^/\s]+)'
    # Pattern for TV show episodes
    episode_pattern = r'(?:tv-shows|tvshows)/details/[^/]+/[^/]+/[^/]+/([^/\s]+)'
    # Pattern for kids content
    kids_pattern = r'kids/(?:kids-movies|kids-shows|kids-videos)/[^/]+/([^/\s]+)'
    # Pattern for movies and other content
    content_pattern = r'(?:movies|originals|videos)/details/[^/]+/([^/\s]+)'
    
    # Try to match web series pattern first
    match = re.search(series_pattern, url)
    if match:
        content_id = match.group(1)
        return content_id
        
    # Try to match web series episode pattern
    match = re.search(web_series_pattern, url)
    if match:
        content_id = match.group(1)
        return content_id
    
    # Try to match kids content pattern
    match = re.search(kids_pattern, url)
    if match:
        content_id = match.group(1)
        return content_id
    
    # Try to match TV show episode pattern
    match = re.search(episode_pattern, url)
    if match:
        content_id = match.group(1)
        return content_id
    
    # Try general content pattern
    match = re.search(content_pattern, url)
    if match:
        content_id = match.group(1)
        return content_id
        
    logger.error(f"Could not extract content ID from URL: {url}")
    raise ValueError(f"Invalid ZEE5 URL format: {url}")

def clean_mpd_url(url: str) -> str:
    """Extract the base MPD URL without query parameters"""
    if not url:
        return url
    
    # Replace manifest.mpd with manifest-connected-4k.mpd only when URL contains 4K
    if "manifest.mpd" in url and "4K" in url.upper():
        url = url.replace("manifest.mpd", "manifest-connected-4k.mpd")
    return url

def get_last_key(keys: list) -> str:
    """Get the last key from the list, usually the content key"""
    if not keys or not isinstance(keys, list):
        return None
    return keys[-1]

def format_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

def ensure_dir(directory: str) -> str:
    """Ensure directory exists and return its path"""
    Path(directory).mkdir(parents=True, exist_ok=True)
    return directory

def clean_filename(filename: str) -> str:
    """Clean filename from invalid characters"""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def get_video_info(mpd_url: str) -> Dict[str, Any]:
    """Get video information using yt-dlp"""
    try:
        cmd = ['yt-dlp', '--dump-json', mpd_url]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
        return {}
    except Exception:
        return {}

def display_content_info(content: Dict[str, Any]) -> None:
    """Display content information in a formatted way"""
    print("\n" + "="*50)
    print(f" Title: {content.get('title', 'N/A')}")
    print(f" Description: {content.get('description', 'N/A')[:200]}...")
    print(f" Duration: {content.get('duration', 'N/A')} seconds")
    print(f" Audio Languages: {', '.join(content.get('audio_languages', []))}")
    print(f" Subtitles: {', '.join(content.get('subtitle_languages', []))}")
    print("="*50 + "\n")

def get_user_choice(options: list, prompt: str) -> Optional[int]:
    """Get user choice from a list of options"""
    for i, option in enumerate(options, 1):
        print(f"{i}. {option}")
    
    try:
        choice = int(input(f"\n{prompt} (enter number): ")) - 1
        if 0 <= choice < len(options):
            return choice
        print(" Invalid selection.")
    except (ValueError, IndexError):
        print(" Invalid input. Please enter a valid number.")
    return None

class Zee5API:
    def __init__(self, use_proxy=USE_PROXY):
        self.base_url = "https://spapi.zee5.com"
        # Initialize with placeholder tokens
        self.bearer_token = None
        self.access_token = None
        self.dd_token = "eyJzY2hlbWFfdmVyc2lvbiI6IjEiLCJvc19uYW1lIjoiTi9BIiwib3NfdmVyc2lvbiI6Ik4vQSIsInBsYXRmb3JtX25hbWUiOiJDaHJvbWUiLCJwbGF0Zm9ybV92ZXJzaW9uIjoiMTA0IiwiZGV2aWNlX25hbWUiOiIiLCJhcHBfbmFtZSI6IldlYiIsImFwcF92ZXJzaW9uIjoiMi41Mi4zMSIsInBsYXllcl9jYXBhYmlsaXRpZXMiOnsiYXVkaW9fY2hhbm5lbCI6WyJTVEVSRU8iXSwidmlkZW9fY29kZWMiOlsiSDI2NCJdLCJjb250YWluZXIiOlsiTVA0IiwiVFMiXSwicGFja2FnZSI6WyJEQVNIIiwiSExTIl0sInJlc29sdXRpb24iOlsiMjQwcCIsIlNEIiwiSEQiLCJGSEQiXSwiZHluYW1pY19yYW5nZSI6WyJTRFIiXX0sInNlY3VyaXR5X2NhcGFiaWxpdGllcyI6eyJlbmNyeXB0aW9uIjpbIldJREVWSU5FX0FFU19DVFIiXSwid2lkZXZpbmVfc2VjdXJpdHlfbGV2ZWwiOlsiTDMiXSwiaGRjcF92ZXJzaW9uIjpbIkhEQ1BfVjEiLCJIRENQX1YyIiwiSERDUF9WMl8xIiwiSERDUF9WMl8yIl19fQ=="
        self.use_proxy = use_proxy
        self.session = None
        self.original_url = None
        
    async def initialize(self):
        """Initialize API with tokens and aiohttp session"""
        # Load tokens properly using await
        self.bearer_token, self.access_token = await load_or_generate_tokens()
        
        # Configure proxy for the session if enabled
        connector = aiohttp.TCPConnector(ssl=False)
        if self.use_proxy:
            self.session = aiohttp.ClientSession(
                connector=connector,
                trust_env=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'},
                proxy=PROXY_URL
            )
            logger.debug(f"Initialized session with proxy: {PROXY_URL}")
        else:
            self.session = aiohttp.ClientSession(
                connector=connector,
                trust_env=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            )
            logger.debug("Initialized session without proxy")
        logger.debug("Zee5API initialized with tokens and session")
        
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()

    async def get_content_details(self, content_id: str) -> Dict[str, Any]:
        """Get content details from ZEE5"""
        # Check if session is initialized
        if not self.session:
            await self.initialize()
            
        logger.info(f"Getting content details for content ID: {content_id}")
        
        # Check if it's a series ID (starts with 0-6)
        if content_id.startswith("0-6"):
            url = f"https://gwapi.zee5.com/content/tvshow/{content_id}"
            params = {
                "translation": "en",
                "country": "IN"
            }
            logger.debug(f"Using TV show URL: {url}")
        else:
            url = f"{self.base_url}/singlePlayback/v2/getDetails/secure"
            
            # Default parameters
            params = {
                "content_id": content_id,
                "device_id": "4OCS6cTntqWafDrE0k7I000000000000",
                "platform_name": "desktop_web",
                "translation": "en",
                "user_language": "en",
                "country": "IN",
                "state": "UP",
                "app_version": "4.14.6",
                "user_type": "premium",
                "check_parental_control": "false",
                "gender": "Male",
                "age_group": "18-24",
                "uid": "288f586d-5697-4234-b784-a2b1722e4198",
                "ppid": "4OCS6cTntqWafDrE0k7I000000000000",
                "version": "12"
            }
            
            # Handle global content differently
            if hasattr(self, 'original_url') and '/global/' in self.original_url:
                params.update({
                    "country": "US",  # Use US as the country for global content
                    "state": "",      # No state for international
                    "user_language": "en"  # Use English for global content
                })
                logger.debug("Using global content parameters")
            
            logger.debug(f"Using single playback URL: {url}")
            
        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"bearer {self.bearer_token}",
            "x-access-token": self.access_token,
            "x-dd-token": self.dd_token,
            "content-type": "application/json",
            "origin": "https://www.zee5.com",
            "referer": "https://www.zee5.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

        data = {
            **params,
            "Authorization": f"bearer {self.bearer_token}",
            "x-access-token": self.access_token,
            "x-dd-token": self.dd_token
        } if not content_id.startswith("0-6") else None

        try:
            logger.debug(f"Making request with proxy: {self.use_proxy}")
            logger.debug(f"Proxy URL: {PROXY_URL if self.use_proxy else 'None'}")
            
            # Create a new connector and session for this request
            connector = aiohttp.TCPConnector(ssl=False, force_close=True)
            proxy_url = PROXY_URL if self.use_proxy else None
            
            async with aiohttp.ClientSession(connector=connector) as session:
                if self.use_proxy:
                    session._proxy = proxy_url
                    session._proxy_auth = None

                if content_id.startswith("0-6"):
                    # For series, use GET request with params
                    async with session.get(url, headers=headers, params=params, proxy=proxy_url, ssl=False) as response:
                        response.raise_for_status()
                        content = await response.json()
                        logger.debug(f"Series response status: {response.status}")
                else:
                    # For episodes/movies, use POST request
                    async with session.post(url, headers=headers, params=params, json=data, proxy=proxy_url, ssl=False) as response:
                        response.raise_for_status()
                        content = await response.json()
                        logger.debug(f"Episode/Movie response status: {response.status}")

                # Save the JSON response to a file
                with open(f"{content_id}_response.json", "w") as f:
                    json.dump(content, f, indent=4)
            logger.debug(f"Response content: {json.dumps(content, indent=2)}")
            
            if content_id.startswith("0-6"):
                # Get episodes from all seasons
                episodes = []
                for season in content.get("seasons", []):
                    season_episodes = season.get("episodes", [])
                    for episode in season_episodes:
                        episode_details = await self.get_content_details(episode.get("id", ""))
                        if episode_details.get("status") == "success":
                            episode_data = episode_details.get("data", {})
                            # Add poster_url to the episode details
                            image_url = episode_data.get('image_url')
                            if image_url:
                                # Check if image_url already has the full URL
                                if image_url.startswith("http"):
                                    poster_url = image_url.replace("list/270x152", "list/1170x658") # Already a full URL
                                else:
                                    # Construct URL for high-res (1170x658) image
                                    poster_url = image_url.replace("list/270x152", "list/1170x658")
                                    poster_url = f"https://akamaividz.zee5.com/resources/{poster_url}"
                            else:
                                poster_url = None

                            # Extract and format episode number as S01Exx
                            orderid = episode.get("orderid")
                            episode_number_formatted = f"S01E{orderid}" if orderid is not None else None

                            episodes.append({
                                "title": episode.get("title"),
                                "id": episode.get("id"),
                                "episode_number": episode_number_formatted,  # Use formatted episode number
                                "duration": episode.get("duration"),
                                "description": episode.get("description", ""),
                                "video_url": episode_data.get("video_url", {}).get("mpd"),
                                "hls_url": episode_data.get("video_url", {}).get("hls"),
                                "subtitles": episode_data.get("subtitles", []),
                                "key_os_details": episode_data.get("key_os_details", {}),
                                "poster_url": poster_url  # Add the poster URL here
                            })
                
                return {
                    "status": "success",
                    "title": content.get("title"),
                    "description": content.get("description"),
                    "seasons": content.get("seasons", []),
                    "episodes": episodes
                }
            
            asset_details = content.get('assetDetails', {})
            if not asset_details:
                logger.error("No asset details found in response")
                return {
                    "status": "error",
                    "message": "No asset details found",
                }
            
            # Get video URLs
            video_urls = asset_details.get('video_url', {})
            logger.debug(f"Video URLs in asset details: {json.dumps(video_urls, indent=2)}")
            
            hls_url = video_urls.get('m3u8', '')
            dash_url = video_urls.get('mpd', '')

            # Get image URL (poster) and construct the URL conditionally
            image_url = asset_details.get('image_url', '')
            if image_url:
                if image_url.startswith("http"):
                    poster_url = image_url.replace("list/270x152", "list/1170x658") # Already a full URL
                else:
                    # Construct URL for high-res (1170x658) image
                    poster_url = image_url.replace("list/270x152", "list/1170x658")
                    poster_url = f"https://akamaividz.zee5.com/resources/{poster_url}"

                asset_details['poster_url'] = poster_url
            else:
                asset_details['poster_url'] = None
            
            # Update asset details with both URLs
            asset_details['video_url'] = {
                'hls': hls_url,
                'dash': dash_url,
                'mpd': dash_url  
            }

            # Get key_os_details
            key_os_details = content.get('keyOsDetails', {})
            if key_os_details:
                asset_details['key_os_details'] = key_os_details
            
            return {
                "status": "success",
                "data": asset_details
            }
        except Exception as e:
            error_message = str(e)
            try:
                # Use a more robust error message handling approach
                if isinstance(error_message, bytes):
                    error_message = error_message.decode('utf-8', errors='replace')
                elif isinstance(error_message, str):
                    error_message = error_message.encode('utf-8', errors='replace').decode('utf-8')
            except:
                error_message = "Error occurred (details cannot be displayed)"
            
            logger.error(f"Error getting content details: {error_message}")
            return {
                "status": "error",
                "message": error_message
            }

    async def get_content_details_and_pssh(self, content_id: str) -> Dict[str, Any]:
        """Gets content details and extracts PSSH in one go."""
        logger.info(f"Getting content details for ID: {content_id}")
        details = await self.get_content_details(content_id)
        logger.debug(f"Content details response: {json.dumps(details, indent=2)}")
        
        if details.get("status") != "success":
            logger.error(f"Failed to get content details: {details.get('message', 'Unknown error')}")
            return details  # Return the error from get_content_details

        data = details.get("data", {})
        video_urls = data.get("video_url", {})
        logger.debug(f"Video URLs found: {json.dumps(video_urls, indent=2)}")
        
        mpd_url = video_urls.get("mpd") or video_urls.get("dash")  # Try both mpd and dash keys
        logger.info(f"MPD URL found: {mpd_url}")
        
        if not mpd_url:
            logger.error("No MPD URL found in video_urls")
            logger.debug(f"Available video URL keys: {list(video_urls.keys())}")
            return {
                "status": "error",
                "message": "No MPD URL found",
                "data": data,
            }

        # Convert to mediacloudfront URL if needed
        mpd_url = get_base_url(mpd_url, content_id)
        logger.info(f"Converted MPD URL: {mpd_url}")

        # Get headers (same as in get_content_details)
        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"bearer {self.bearer_token}",
            "x-access-token": self.access_token,
            "x-dd-token": self.dd_token,
            "content-type": "application/json",
            "origin": "https://www.zee5.com",
            "referer": "https://www.zee5.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

        pssh = await extract_pssh(mpd_url, content_id, headers, self.use_proxy)
        logger.info(f"PSSH extracted: {bool(pssh)}")
        
        if pssh:
            details["pssh"] = pssh  # Add PSSH to the details
            return details
        else:
            return {
                "status": "error",
                "message": "PSSH extraction failed",
                "data": data,
            }

    async def get_asset_details(self, content_id: str) -> dict:
        """Get asset details for a content ID"""
        try:
            if not self.session:
                await self.initialize()
                
            url = f"{self.base_url}/content/details/{content_id}"
            headers = {
                "accept": "application/json",
                "accept-encoding": "gzip, deflate, br",
                "accept-language": "en-US,en;q=0.9",
                "authorization": f"bearer {self.bearer_token}",
                "x-access-token": self.access_token,
                "x-dd-token": self.dd_token,
                "content-type": "application/json",
                "origin": "https://www.zee5.com",
                "priority": "u=1, i",
                "referer": "https://www.zee5.com/",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            }
            
            proxy = PROXY_URL if self.use_proxy else None
            async with self.session.get(url, headers=headers, proxy=proxy) as response:
                response.raise_for_status()
                data = await response.json()
            
            if not data:
                return {}

            # Save the JSON response to a file
            with open(f"{content_id}.json", "w") as f:
                json.dump(data, f, indent=4)
            # Extract required details
            asset_details = {}
            asset_details["id"] = content_id
            asset_details["title"] = data.get("title", "")
            
            # Get key_os_details for TV serials
            if content_id.startswith("0-1-"):
                key_os_details = data.get("keyOsDetails", {})
                if isinstance(key_os_details, dict):
                    asset_details["key_os_details"] = key_os_details
                else:
                    asset_details["key_os_details"] = {}
            else:
                # For movies and other content
                asset_details["keyOsDetails"] = data.get("keyOsDetails", {})
                
            # Get video details
            asset_details["video_details"] = data.get("video_details", {})
            
            # Get DRM details
            asset_details["drm_key_details"] = data.get("drm_key_details", {})
            
            return asset_details
        except Exception as e:
            logger.error(f"Error getting asset details: {str(e)}")
            return {}

    async def get_drm_info(self, content_id: str) -> Dict[str, Any]:
        """Gets DRM information including license URL, PSSH, and keys."""
        content_info = await self.get_content_details_and_pssh(content_id)
        if content_info.get("status") != "success":
            return {
                "status": "error",
                "message": content_info.get("message", "Failed to get content info"),
            }

        data = content_info.get("data", {})
        mpd_url = data.get("video_url", {}).get("mpd")
        pssh = content_info.get("pssh")
        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US,en;q=0.9",
            "authorization": f"bearer {self.bearer_token}",
            "x-access-token": self.access_token,
            "x-dd-token": self.dd_token,
            "content-type": "application/json",
            "origin": "https://www.zee5.com",
            "priority": "u=1, i",
            "referer": "https://www.zee5.com/",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

        if not mpd_url or not pssh:
            return {
                "status": "error",
                "message": "MPD URL or PSSH not found",
                "license_url": None,
                "pssh": pssh,
                "keys": None,
            }

        keys = await get_content_keys(mpd_url, data, content_id, headers, self.session, self.use_proxy, pssh)
        license_url = "https://spapi.zee5.com/widevine/getLicense"  # Standard ZEE5 license URL

        if isinstance(keys, dict) and "error" in keys:
            return {
                "status": "error",
                "message": keys["error"],
                "license_url": license_url,
                "pssh": pssh,
                "keys": None,
            }

        return {
            "status": "success",
            "license_url": license_url,
            "pssh": pssh,
            "keys": keys,
        }

def get_base_url(url: str, content_id: str) -> str:
    """Extract path from URL and add correct base URL based on content type while preserving auth params"""
    if not url:
        return url
    try:
        parsed = urlparse(url)
        path = parsed.path
        if path.startswith('/'):
            path = path[1:]
            
        # Preserve authentication parameters
        auth_params = []
        query_params = parse_qs(parsed.query)
        for key in ['hdnea', 'session_id', 'c3.ri', 'req_id']:
            if key in query_params:
                auth_params.append(f"{key}={query_params[key][0]}")
        
        auth_string = '?' + '&'.join(auth_params) if auth_params else ''
            
        # TV serials start with 0-1
        # Web series start with 0-6
        # Movies start with 0-0
        # Kids content starts with 0-2
        if content_id.startswith(("0-1-", "0-6-", "0-2-")):  # TV serials, web series, kids
            return f"https://mediacloudfront.zee5.com/{path}{auth_string}"
        else:  # Movies and other content
            # Use the domain from the original URL
            return f"{parsed.scheme}://{parsed.netloc}/{path}{auth_string}"
    except:
        return url

async def extract_movie_pssh(mpd_url: str, content_id: str, headers: dict, use_proxy: bool) -> Optional[str]:
    """Extract PSSH from movie MPD content (0-0-)"""
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        proxy = PROXY_URL if use_proxy else None
        aiohttp_headers = dict(headers)
        aiohttp_headers['accept-encoding'] = 'gzip, deflate'
        async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
            async with session.get(mpd_url, headers=aiohttp_headers, proxy=proxy) as response:
                response.raise_for_status()
                mpd_content = await response.text()
        
        # Movies use Widevine PSSH with ContentProtection tag
        widevine_uuid = "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"
        pssh_pattern = f'<ContentProtection.*?schemeIdUri="urn:uuid:{widevine_uuid}".*?<cenc:pssh>([^<]+)</cenc:pssh>'
        pssh_match = re.search(pssh_pattern, mpd_content, re.DOTALL)
        
        if pssh_match:
            return pssh_match.group(1)
        return None
    except Exception as e:
        logger.error(f"Error extracting movie PSSH: {str(e)}, url='{mpd_url}'")
        return None

async def extract_tv_serial_pssh(mpd_url: str, content_id: str, headers: dict, use_proxy: bool) -> Optional[str]:
    """Extract PSSH from TV serial MPD content (0-1-)"""
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        proxy = PROXY_URL if use_proxy else None
        aiohttp_headers = dict(headers)
        aiohttp_headers['accept-encoding'] = 'gzip, deflate'
        async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
            async with session.get(mpd_url, headers=aiohttp_headers, proxy=proxy) as response:
                response.raise_for_status()
                mpd_content = await response.text()
        
        # TV serials use Widevine PSSH with cenc namespace
        widevine_uuid = "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"
        pssh_pattern = f'<ContentProtection.*?schemeIdUri="urn:uuid:{widevine_uuid}".*?<cenc:pssh>([^<]+)</cenc:pssh>'
        pssh_match = re.search(pssh_pattern, mpd_content, re.DOTALL)
        
        if pssh_match:
            return pssh_match.group(1)
        return None
    except Exception as e:
        logger.error(f"Error extracting TV serial PSSH: {str(e)}, url='{mpd_url}'")
        return None

async def extract_web_series_pssh(mpd_url: str, content_id: str, headers: dict, use_proxy: bool) -> Optional[str]:
    """Extract PSSH from web series MPD content (0-6-)"""
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        proxy = PROXY_URL if use_proxy else None
        aiohttp_headers = dict(headers)
        aiohttp_headers['accept-encoding'] = 'gzip, deflate'
        async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
            async with session.get(mpd_url, headers=aiohttp_headers, proxy=proxy) as response:
                response.raise_for_status()
                mpd_content = await response.text()
        
        # Web series use simple pssh tag
        pssh_match = re.search(r'pssh>([^<]+)</pssh', mpd_content)
        
        if pssh_match:
            return pssh_match.group(1)
        return None
    except Exception as e:
        logger.error(f"Error extracting web series PSSH: {str(e)}, url='{mpd_url}'")
        return None

async def extract_pssh(mpd_url: str, content_id: str, headers: dict, use_proxy: bool) -> Optional[str]:
    """Main function to extract PSSH based on content type"""
    if content_id.startswith("0-0-"):  # Movies
        return await extract_movie_pssh(mpd_url, content_id, headers, use_proxy)
    elif content_id.startswith("0-1-"):  # TV serials
        return await extract_tv_serial_pssh(mpd_url, content_id, headers, use_proxy)
    elif content_id.startswith("0-6-"):  # Web series
        return await extract_web_series_pssh(mpd_url, content_id, headers, use_proxy)
    else:
        logger.error(f"Unknown content type for ID: {content_id}")
        return None

def extract_movie_token(key_os_details: Dict) -> Optional[str]:
    """Extract token for movies (0-0-)"""
    if not key_os_details:
        return None
        
    token = key_os_details.get("sdrm", "")
    if not token:
        logger.error("No SDRM token found for movie")
        return None
        
    return token

def extract_tv_serial_token(key_os_details: Dict) -> Optional[str]:
    """Extract token for TV serials (0-1-)"""
    if not key_os_details:
        return None
        
    # For TV serials, token is in sdrm field just like movies
    token = key_os_details.get("sdrm", "")
    if not token:
        logger.error("No SDRM token found for TV serial")
        return None
        
    return token

def extract_web_series_token(key_os_details: Dict) -> Optional[str]:
    """Extract token for web series (0-6-)"""
    if not key_os_details:
        return None
        
    token = key_os_details.get("token", "")
    if not token:
        logger.error("No token found for web series")
        return None
        
    return token

def prepare_token(token: str) -> Dict[str, str]:
    """Prepare token for API request by adding Nagra_ prefix if needed"""
    if not token:
        return {"error": "No token provided"}
        
    if not token.startswith("Nagra_"):
        token = f"Nagra_{token}"
        
    nl_value = token[6:] if token.startswith("Nagra_") else token
    
    return {
        "customdata": token,
        "nl": nl_value
    }

def get_content_token(content_id: str, key_os_details: Dict) -> Dict[str, str]:
    """Get token based on content type"""
    if not content_id or not key_os_details:
        return {"error": "Missing content ID or key_os_details"}
        
    token = None
    
    # Extract token based on content type
    if content_id.startswith("0-0-"):  # Movies
        token = extract_movie_token(key_os_details)
    elif content_id.startswith("0-1-"):  # TV serials
        token = extract_tv_serial_token(key_os_details)
    elif content_id.startswith("0-6-"):  # Web series
        token = extract_web_series_token(key_os_details)
    else:
        return {"error": f"Unknown content type for ID: {content_id}"}
        
    if not token:
        return {"error": "Failed to extract token"}
        
    return prepare_token(token)

def get_series_episodes(content_details: dict) -> list:
    """Extract episode details from series content details"""
    return content_details.get("episodes", [])

def get_episode_keys(episode_id: str):
    """Get keys for a specific episode"""
    zee5_api = Zee5API()
    content_details = zee5_api.get_content_details(episode_id)
    
    if not content_details or content_details.get("status") != "success":
        print("Failed to get episode details")
        return
        
    asset_details = content_details.get("data", {})
    mpd_url = asset_details.get("video_url", {}).get("mpd")
    if not mpd_url:
        print("No MPD URL found")
        return
        
    get_content_keys(mpd_url, asset_details, episode_id, {}, USE_PROXY, "")

async def get_content_keys(mpd_url: str, asset_details: Dict, content_id: str, headers: dict, session: aiohttp.ClientSession, use_proxy: bool, pssh: str = None) -> Dict:
    """Get content keys from license server"""
    try:
        # Init CDM
        device = Device.load(DEVICE_PATH)
        cdm = Cdm.from_device(device)
        
        if not pssh:
            # Extract PSSH from MPD
            if content_id.startswith("0-0-"):  # Movie
                pssh = await extract_movie_pssh(mpd_url, content_id, headers, use_proxy)
            elif content_id.startswith("0-1-"):  # TV Serial
                pssh = await extract_tv_serial_pssh(mpd_url, content_id, headers, use_proxy)
            elif content_id.startswith("0-6-"):  # Web Series
                pssh = await extract_web_series_pssh(mpd_url, content_id, headers, use_proxy)
                
        if not pssh:
            logger.error("Failed to extract PSSH")
            return {"error": "PSSH Not Found"}
            
        # Get key_os_details
        key_os_details = asset_details.get("key_os_details", {})
        if not key_os_details:
            return {"error": "No Key Details Found"}
            
        # Get token using our new module
        token_data = get_content_token(content_id, key_os_details)
        if "error" in token_data:
            return {"error": token_data["error"]}
            
        # Generate license request
        session_id = cdm.open()
        try:
            challenge = cdm.get_license_challenge(session_id, PSSH(pssh))
            if not challenge:
                return {"error": "Failed to generate challenge"}

            # Prepare headers for license request
            license_headers = {
                "accept": "*/*",
                "accept-encoding": "gzip, deflate, br",
                "accept-language": "en-US,en;q=0.5",
                "content-type": "application/octet-stream",
                "customdata": token_data["customdata"],
                "nl": token_data["nl"],
                "origin": "https://www.zee5.com",
                "referer": "https://www.zee5.com/",
                "x-z5-appversion": "4.17.1",
                "x-z5-appplatform": "desktop_web",
                "x-user-type": "premium",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "connection": "keep-alive"
            }

            # Get license with proxy if enabled
            if use_proxy:
                connector = aiohttp.TCPConnector(ssl=False)
                async with aiohttp.ClientSession(connector=connector) as license_session:
                    license_session._proxy = PROXY_URL
                    license_session._proxy_auth = None
                    async with license_session.post(
                        "https://spapi.zee5.com/widevine/getLicense",
                        headers=license_headers,
                        data=challenge
                    ) as response:
                        if response.status != 200:
                            return {"error": f"License Request Failed (Status: {response.status})"}
                        license_data = await response.read()
            else:
                async with session.post(
                    "https://spapi.zee5.com/widevine/getLicense",
                    headers=license_headers,
                    data=challenge
                ) as response:
                    if response.status != 200:
                        return {"error": f"License Request Failed (Status: {response.status})"}
                    license_data = await response.read()

            # Parse license and get keys
            cdm.parse_license(session_id, license_data)
            keys = []
            for key in cdm.get_keys(session_id):
                keys.append(f"{key.kid.hex}:{key.key.hex()}")
            return keys

        except Exception as e:
            return {"error": f"Key Request Failed: {str(e)}"}
        finally:
            if 'session_id' in locals():
                cdm.close(session_id)
                
    except Exception as e:
        return {"error": f"Key Processing Failed: {str(e)}"}

async def get_episode_keys_async(episode: Dict, series_info: Dict, content_id: str, zee5_api: Zee5API):
    """Get keys for an episode asynchronously"""
    # Get content details and PSSH together
    content_info = await zee5_api.get_content_details_and_pssh(episode['id'])
    if content_info.get("status") == "error":
        # Handle the error appropriately, e.g., log it
        episode_keys = {"error": content_info.get('message')}
        return episode_keys
    else:
        content_details = content_info.get("data", {})
        pssh = content_info.get("pssh")
        headers = {
                "accept": "application/json",
                "accept-encoding": "gzip, deflate, br",
                "accept-language": "en-US,en;q=0.9",
                "authorization": f"bearer {zee5_api.bearer_token}",
                "x-access-token": zee5_api.access_token,
                "x-dd-token": zee5_api.dd_token,
                "content-type": "application/json",
                "origin": "https://www.zee5.com",
                "priority": "u=1, i",
                "referer": "https://www.zee5.com/",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            }
        episode_keys = await get_content_keys(episode['video_url'], content_details, episode['id'], headers, zee5_api.session, zee5_api.use_proxy, pssh)

    # Find and update the episode in series_info
    for ep in series_info['episodes']:
        if ep['episode_number'] == episode['episode_number']:
            if isinstance(episode_keys, dict) and 'error' in episode_keys:
                ep['keys'] = episode_keys['error']  # Store error message
            else:
                ep['keys'] = episode_keys
            break
    
    return episode_keys

async def get_web_series_details(url: str, zee5_api: Zee5API):
    """Get web series details"""
    try:
        # Extract content ID
        content_id = extract_content_id(url)
        if not content_id:
            return {"status": "error", "message": "Failed to extract content ID"}
            
        # Get content details
        content_details = await zee5_api.get_content_details(content_id)
        
        if not content_details or content_details.get("status") != "success":
            return {"status": "error", "message": "Failed to get content details"}
            
        data = content_details.get("data", {})
        video_urls = data.get("video_url", {})
        if not video_urls:
            return {"status": "error", "message": "No video URLs found"}

        # Get MPD URL and keys
        mpd_url = video_urls.get("mpd")
        keys = None
        if mpd_url:
            # Convert to mediacloudfront URL if needed
            mpd_url = get_base_url(mpd_url, content_id)
            # Apply clean_mpd_url to replace manifest.mpd with manifest-connected-4k.mpd
            mpd_url = clean_mpd_url(mpd_url)
            
            # Get headers for MPD and license requests
            headers = {
                "accept": "application/json",
                "accept-encoding": "gzip, deflate, br",
                "accept-language": "en-US,en;q=0.9",
                "authorization": f"bearer {zee5_api.bearer_token}",
                "x-access-token": zee5_api.access_token,
                "x-dd-token": zee5_api.dd_token,
                "content-type": "application/json",
                "origin": "https://www.zee5.com",
                "priority": "u=1, i",
                "referer": "https://www.zee5.com/",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            }
            
            # Get keys
            keys = await get_content_keys(mpd_url, data, content_id, headers, zee5_api.session, zee5_api.use_proxy, "")

        return {
            "status": "success",
            "content_url": url,
            "platform": "ZEE5",
            "content_id": content_id,
            "type": "web_series",
            "title": data.get("tvshow_name", "") if data.get("asset_subtype") == "episode" else data.get("title", ""),
            "episode_title": data.get("title", "") if data.get("asset_subtype") == "episode" else "",
            "season": data.get("season_number", ""),
            "episode": data.get("orderid", ""),
            "episode_number": f"S01E{str(data.get('orderid', '1'))}",
            "poster_url": data.get('poster_url'),
            "streams": {
                "hls": video_urls.get("hls"),
                "dash": mpd_url if mpd_url else None
            },
            "subtitles": [
                {"language": sub.get("language", ""), "url": sub.get("url", "")}
                for sub in data.get("subtitle_url", [])
                if sub.get("language") and sub.get("url")
            ],
            "drm": {
                "needs_decryption": True if mpd_url else False,
                "keys": get_last_key(keys) if keys and not isinstance(keys, dict) else None,
                "error": keys.get("error") if isinstance(keys, dict) and "error" in keys else None
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def show_series_summary(series_info: Dict, episodes_queue: Queue, input_url: str, waiting: bool = False):
    """Show series summary with real-time updates"""
    while True:
        print("\033[H\033[J")  # Clear screen
        print("="*50)
        print(f"URL: {input_url}")
        print("="*50)
        print("SERIES SUMMARY")
        print("="*50)
        print(f"Title: {series_info['title']}")
        print(f"Total Episodes: {len(series_info['episodes'])}")
        
        if waiting:
            print("\nWe are in a wait time between episodes request of key to avoid rate limit.")
            
        print("\nEpisode Details:")
        print("-"*50)
        
        for episode in series_info["episodes"]:
            print(f"\nEpisode {episode['episode_number']}: {episode['title']}")
            if episode.get('poster_url'):  # Check if poster_url exists
                print(f"Poster URL: {episode['poster_url']}") # then print
            if episode.get('mpd'):
                print(f"MPD: {get_base_url(episode['mpd'], episode['id'])}")
            if episode.get('keys') is None:
                print("Keys: FETCHING...")
            elif isinstance(episode['keys'], str):  # Error message
                print(f"Keys: {episode['keys']}")  # Show error message
            else:
                last_key = get_last_key(episode['keys'])
                if last_key:
                    print(f"Keys: {last_key}")
            print("-"*50)
        
        if episodes_queue.empty():
            break
            
        time.sleep(1)  # Update every second

async def get_keys(url: str):
    # Extract content ID
    content_id = extract_content_id(url)
    if not content_id:
        return {"status": "error", "message": "Failed to extract content ID"}

    # Initialize ZEE5 API, allow disabling proxy
    zee5_api = Zee5API(use_proxy=USE_PROXY)
    # Store the original URL for context-aware processing
    zee5_api.original_url = url
    await zee5_api.initialize()  # Initialize the session

    try:
        # Get content details and PSSH together
        content_info = await zee5_api.get_content_details_and_pssh(content_id)
        if content_info.get("status") == "error":
            return {"status": "error", "message": content_info.get('message')}

        content_details = content_info.get("data", {})
        pssh = content_info.get("pssh")  # Get the extracted PSSH

        # Check content type and get appropriate details
        if content_id.startswith("0-6"):  # Series
            return await get_web_series_details(url, zee5_api)
        elif content_id.startswith("0-1-"):  # TV Show Episode
            return await get_web_series_details(url, zee5_api)
        else:  # Movie or other content
            data = content_details
            video_url = data.get("video_url", {})
            
            # Get and clean MPD URL and keys
            mpd_url = video_url.get("dash", "")
            keys = None
            if mpd_url:
                mpd_url = get_base_url(mpd_url, content_id)
                # Apply clean_mpd_url to replace manifest.mpd with manifest-connected-4k.mpd
                mpd_url = clean_mpd_url(mpd_url)
                headers = {
                    "accept": "application/json",
                    "accept-encoding": "gzip, deflate, br",
                    "accept-language": "en-US,en;q=0.9",
                    "authorization": f"bearer {zee5_api.bearer_token}",
                    "x-access-token": zee5_api.access_token,
                    "x-dd-token": zee5_api.dd_token,
                    "content-type": "application/json",
                    "origin": "https://www.zee5.com",
                    "priority": "u=1, i",
                    "referer": "https://www.zee5.com/",
                    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                }
                keys = await get_content_keys(mpd_url, data, content_id, headers, zee5_api.session, zee5_api.use_proxy, pssh)

            return {
                "status": "success",
                "content_url": url,
                "platform": "ZEE5",
                "title": data.get("tvshow_name", "") if data.get("asset_subtype") == "episode" else data.get("title", ""),
                "episode_title": data.get("title", "") if data.get("asset_subtype") == "episode" else "",
                "content_id": content_id,
                "episode_number": f"S01E{str(data.get('orderid', '1'))}",
                "thumbnail": data.get("poster_url", ""),
                "streams": {
                    "hls": video_url.get("hls", ""),
                    "dash": mpd_url
                },
                "drm": {
                    "needs_decryption": True,
                    "license_url": "https://spapi.zee5.com/widevine/getLicense",
                    "keys": keys
                }
            }

    finally:
        # Close the session when done
        await zee5_api.close()

async def process_url(url: str) -> dict:
    """Global entry point for processing ZEE5 URLs.
    Args:
        url (str): ZEE5 URL to process
    Returns:
        dict: Formatted content information
    """
    try:
        # Extract content ID
        content_id = extract_content_id(url)
        if not content_id:
            return {"status": "error", "message": "Failed to extract content ID"}
            
        # If it's a TV show URL (0-6-), get the episode ID from the URL
        if "/0-6-" in url and "/0-1-" in url:
            # Extract the episode ID instead of show ID
            episode_pattern = r'(?:tvshows|shows)/details/[^/]+/(?:[^/]+)/[^/]+/([0-1][^/\s]+)'
            match = re.search(episode_pattern, url)
            if match:
                content_id = match.group(1)

        # Initialize ZEE5 API
        zee5_api = Zee5API(use_proxy=USE_PROXY)
        # Store the original URL for context-aware processing
        zee5_api.original_url = url
        await zee5_api.initialize()

        try:
            # Get content details and PSSH together
            result = await get_keys(url)
            
            if not result or result.get("status") != "success":
                return {"status": "error", "message": result.get("message", "Failed to get content info")}

            # Get dash URL and apply clean_mpd_url
            dash_url = result.get("streams", {}).get("dash", "")
            if dash_url:
                dash_url = clean_mpd_url(dash_url)

            # Format the response
            info = {
                "status": "success",
                "content_url": url,
                "platform": "ZEE5",
                "title": result.get("title", ""),
                "episode_title": result.get("episode_title", ""),
                "content_id": content_id,
                "episode_number": f"S01E{str(result.get('episode', '1'))}",
                "thumbnail": result.get("poster_url", ""),
                "streams": {
                    "hls": result.get("streams", {}).get("hls", ""),
                    "dash": dash_url
                },
                "drm": {
                    "needs_decryption": result.get("drm", {}).get("needs_decryption", True),
                    "license_url": "https://spapi.zee5.com/widevine/getLicense",
                    "keys": result.get("drm", {}).get("keys")
                }
            }
            
            return info

        finally:
            # Always close the session
            await zee5_api.close()

    except Exception as e:
        logger.error(f"Error processing ZEE5 URL: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    # Set logging level to DEBUG
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Test proxy connection before proceeding
    if USE_PROXY:
        logger.info(f"Testing proxy connection to: {PROXY_URL}")
        import requests
        try:
            test_response = requests.get("https://api.ipify.org?format=json", proxies=PROXIES, verify=False)
            logger.info(f"Proxy test successful. IP: {test_response.json()['ip']}")
        except Exception as e:
            logger.error(f"Proxy test failed: {str(e)}")
            logger.warning("Continuing with script execution anyway...")
    
    url = input("Enter ZEE5 URL: ")
    result = asyncio.run(process_url(url))
    print("\nFinal Result:")
    print(json.dumps(result, indent=2))  # Pretty print the JSON output
