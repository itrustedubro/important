import asyncio
import sys
import aiohttp
import re
import uuid
import json
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
from helpers.config import PROXY_URL, USE_PROXY, AUTHORIZATION_TOKEN, SESSION_ID, DEVICE_ID

# API endpoints
SONYLIV_API_BASE = "https://apiv2.sonyliv.com/AGL/3.5/SR/ENG/WEB/IN/UP/DETAIL-V2"
AIRTEL_API_BASE = "https://content.airtel.tv/app/v4/content"

# Proxy configuration
proxies = {'http': PROXY_URL, 'https': PROXY_URL} if USE_PROXY and PROXY_URL else None

# Common headers
DEFAULT_SONYLIV_HEADERS = {
    'authority': 'apiv2.sonyliv.com',
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'app_version': '3.6.3',
    'device_id': DEVICE_ID,
    'referer': 'https://www.sonyliv.com/',
}

DEFAULT_AIRTEL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9"
}

# MPD Headers
mpd_headers = {
    'access-control-allow-origin': '*',
    'accept': '*/*',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'en-US,en;q=0.9',
    'origin': 'https://www.sonyliv.com',
    'referer': 'https://www.sonyliv.com/',
    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'x-playback-session-id': DEVICE_ID
}

# Format options mapping
FORMAT_OPTIONS = {
    1: {"codec": "H265", "range_type": "DOLBY_VISION", "display_range": "DOLBY-VISION"},
    2: {"codec": "H265", "range_type": "HDR10", "display_range": "HDR10"},
    3: {"codec": "H265", "range_type": "HLG", "display_range": "SDR"},
    4: {"codec": "H264", "range_type": "UNKNOWN", "display_range": "NORMAL"}
}

# SonyLivFormats class for fetching MPD URLs
class SonyLivFormats:
    """
    Service code for SonyLiv streaming service (https://sonyliv.com).
    """

    def __init__(self):
        self.bearer_token = AUTHORIZATION_TOKEN
        self.session = requests.Session()
        self.set_proxy(PROXY_URL)
        self.session_id = SESSION_ID
        self.device_id = DEVICE_ID
        self.security_token = None
        self.state_code = None
        self.city = None
        self.channelpartnerid = None
        self.contact_id = "1"  # Default contact ID

    def get_device_id(self):
        return str(uuid.uuid4())

    def initialize(self):
        if not self.security_token:
            self.security_token = self.get_security_token()
            self.state_code, self.city, self.channelpartnerid = self.get_ULD()

    def set_proxy(self, proxy):
        """Formats and sets the proxy correctly for requests."""
        if proxy:
            self.session.proxies.update({
                "http": proxy,
                "https": proxy
            })

    def get_security_token(self):
        response = self.session.get(
            url='https://apiv2.sonyliv.com/AGL/1.5/A/ENG/FIRE_TV/IN/GETTOKEN',
            headers={
                "Host": "apiv2.sonyliv.com",
                "user-agent": "okhttp/3.14.9"
            }
        )
        return response.json()["resultObj"]

    def get_common_headers(self):
        """Get common headers used in multiple requests"""
        return {
            "Content-Type": "application/json",
            "x-via-device": "true",
            "Host": "apiv2.sonyliv.com",
            "Authorization": self.bearer_token,
            "session-id": self.session_id,
            "user-agent": "com.onemainstream.sonyliv.android/8.95 (Android 7.1.2; en_IN; AFTMM; Build/NS6281 )",
            "security_token": self.security_token,
            "device_id": self.device_id,
        }

    def get_ULD(self):
        headers = {
            **self.get_common_headers(),
            "build_number": "10491",
            "app_version": "6.12.35",
        }
        # Remove Authorization as it's not needed for this request
        headers.pop("Authorization", None)
        
        response = self.session.get(
            url="https://apiv2.sonyliv.com/AGL/1.5/A/ENG/FIRE_TV/IN/USER/ULD",
            headers=headers
        )
        result = response.json()["resultObj"]
        return result.get("state_code"), result.get("city"), result.get("channelPartnerID")

    def get_license_url(self, content_id):
        response = self.session.post(
            url=f'https://apiv2.sonyliv.com/AGL/2.4/SR/ENG/FIRE_TV/IN/{self.state_code}/CONTENT/GETLAURL',
            headers=self.get_common_headers(),
            json={
                "actionType": "play",
                "assetId": content_id,
                "browser": "chrome",
                "deviceId": self.device_id,
                "os": "android",
                "platform": "web"
            }
        )
        return response.json().get('resultObj', {}).get('laURL', "")

    def get_available_formats(self):
        """Returns available format options without fetching actual URLs"""
        return [
            {"name": "DOLBY-VISION", "codec": "H265", "index": 1},
            {"name": "HDR10", "codec": "H265", "index": 2},
            {"name": "SDR", "codec": "H265", "index": 3},
            {"name": "NORMAL", "codec": "H264", "index": 4}
        ]
    
    def get_specific_format(self, content_id, format_choice):
        """Get a specific format based on user choice"""
        self.initialize()
        
        if format_choice not in FORMAT_OPTIONS:
            print(f"Invalid format choice: {format_choice}")
            return None
            
        format_info = FORMAT_OPTIONS[format_choice]
        video_codec = format_info["codec"]
        range_type = format_info["range_type"]
        display_range = format_info["display_range"]
        
        license_url = self.get_license_url(content_id)
        
        # Skip HDR formats if license URL is not available
        if not license_url and (display_range == "DOLBY-VISION" or display_range == "HDR10"):
            print(f"Cannot fetch {display_range} format due to missing license URL")
            return None
            
        print(f"Fetching {display_range} format with {video_codec} codec...")
        
        supp_codec = "H264,AV1,AAC" if video_codec == "H264" else "HEVC,H264,AAC,EAC3,AC3,ATMOS"
        headers = {
            **self.get_common_headers(),
            'Td_client_hints': f'{{"device_make":"Amazon","device_model":"AFTMM","display_res":"2160","viewport_res":"2160","supp_codec":"{supp_codec}","audio_decoder":"EAC3,AAC,AC3,ATMOS","hdr_decoder":"{range_type}","td_user_useragent":"com.onemainstream.sonyliv.android/8.95 (Android 7.1.2; en_IN; AFTMM; Build/NS6281 )"}}'
        }
        
        try:
            playback_response = self.session.post(
                url=f"https://apiv2.sonyliv.com/AGL/3.3/SR/ENG/SONY_ANDROID_TV/IN/{self.state_code}/CONTENT/VIDEOURL/VOD/{content_id}?kids_safe=false&contactId={self.contact_id}",
                headers=headers
            )
            response_json = playback_response.json()
            result_obj = response_json.get("resultObj", {})
            mpd_url = result_obj.get("videoURL", "")
            subtitle_list = result_obj.get("subtitle", [])

            if mpd_url:
                print(f"Found {display_range} format URL")
                return {
                    "url": mpd_url,
                    "video_codec": video_codec,
                    "dynamic_range": display_range,
                    "license_url": license_url,
                    "device_id": self.device_id,
                    "subtitle_list": subtitle_list  # Add subtitle list to the return value
                }
            else:
                print(f"No URL found for {display_range} format")
                return None
                
        except Exception as e:
            print(f"Error fetching {display_range} URL: {str(e)}")
            return None

# Helper functions
def extract_title_from_parts(parts, remove_last=True):
    """Extract title from URL parts"""
    title_parts = parts.split('-')[:-1] if remove_last else parts.split('-')
    return ' '.join(title_parts).title()

def extract_numeric_id(content_id):
    """Extract numeric part from content ID"""
    return content_id.split('_')[-1] if '_' in content_id else content_id

def extract_content_id(url):
    """Extract content ID from SonyLIV URL"""
    url = url.split('?')[0].rstrip('/')
    parts = url.split('/')
    last_part = parts[-1] if parts else ""
    
    # Content type detection
    is_movie = any(x in url for x in ['/movies/', '/movie/'])
    is_show = any(x in url for x in ['/shows/', '/show/'])
    is_sports = any(x in url for x in ['/sports/', '/sport/', '/live-sport/'])
    
    # Default return values
    content_id = None
    is_episode = False
    season = None
    episode = None
    title = None
    show_bundle_id = None
    
    if is_movie:
        content_id = last_part.split('-')[-1]
        if content_id.isdigit():
            title = extract_title_from_parts(last_part)
            return content_id, False, None, None, title, None
    
    if is_show:
        # Direct content ID pattern (e.g., /karam-din-1000139592)
        direct_content_match = re.search(r'-(\d{9,10})$', last_part)
        if direct_content_match:
            content_id = direct_content_match.group(1)
            title = extract_title_from_parts(last_part)
            
            # Extract show bundle ID if available
            if len(parts) >= 3:
                show_part = parts[-2]
                bundle_match = re.search(r'-(\d+)$', show_part)
                if bundle_match:
                    show_bundle_id = bundle_match.group(1)
                    title = extract_title_from_parts(show_part)
            
            return content_id, True, None, None, title, show_bundle_id
        
        # Season/episode format (e.g., /show-123/1-5 for S01E05)
        season_match = re.search(r'(\d+)-(\d+)$', last_part)
        if season_match:
            bundle_id = parts[-2].split('-')[-1]
            season = int(season_match.group(1))
            episode = int(season_match.group(2))
            title = extract_title_from_parts(parts[-2])
            return bundle_id, True, season, episode, title, bundle_id
        
        # Episode ID format
        episode_id = last_part.split('-')[-1]
        if episode_id.isdigit():
            show_bundle_id = parts[-2].split('-')[-1] if len(parts) >= 3 else None
            title = extract_title_from_parts(parts[-2])
            return episode_id, True, None, None, title, show_bundle_id
    
    if is_sports:
        content_id = last_part.split('-')[-1]
        if content_id.isdigit():
            title = extract_title_from_parts(last_part)
            bundle_id = parts[-2].split('-')[-1] if len(parts) >= 3 else None
            return bundle_id, False, None, None, title, bundle_id
    
    return None, False, None, None, None, None

async def make_api_request(session, url, headers=None, params=None):
    """Make API request with error handling"""
    try:
        async with session.get(url, headers=headers, params=params, proxy=proxies['http'] if proxies else None) as response:
            return await response.json() if response.status == 200 else None
    except Exception as e:
        print(f"API request error: {str(e)}")
        return None

async def get_api_data(session, url, headers, params=None):
    """Generic function to get API data"""
    return await make_api_request(session, url, headers, params)

async def get_poster_url(metadata):
    """Extract poster URL from metadata"""
    poster_url = metadata.get('posterUrl', '')
    if not poster_url:
        emf_attributes = metadata.get('emfAttributes', {})
        if emf_attributes:
            for key in ('img_cover_3840_2160', 'landscape_thumb', 'portrait_thumb'):
                if emf_attributes.get(key):
                    return emf_attributes[key]
    return poster_url

async def get_actual_content_id(bundle_id, session=None):
    """Get actual content ID from bundle ID"""
    try:
        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True
        
        url_api = f"{SONYLIV_API_BASE}/{bundle_id}"
        
        params = {
            'kids_safe': 'false',
            'from': '0', 
            'to': '9',
            'segment_id': 'AB_DetailPage_Disable',
            'utm_source': 'https://www.sonyliv.com/',
            'utm_medium': 'none'
        }
        
        custom_headers = {
            **DEFAULT_SONYLIV_HEADERS,
            'origin': 'https://www.sonyliv.com',
            'session_id': SESSION_ID,
            'platform': 'web',
            'x-platform': 'web',
            'x-via-device': 'true',
            'security_token': SonyLivFormats().get_security_token()
        }
        
        data = await get_api_data(session, url_api, custom_headers, params)
        
        if close_session:
            await session.close()
            
        if not data or not data.get('resultObj') or not data['resultObj'].get('containers'):
            return None, None
            
        container = data['resultObj']['containers'][0]
        
        # Get poster URL from metadata
        metadata = container.get('metadata', {})
        poster_url = await get_poster_url(metadata)
        
        # Use the first nested container's ID if available
        nested_containers = container.get('containers', [])
        content_id = nested_containers[0].get('id') if nested_containers else container.get('id')
        
        return content_id, poster_url
                
    except Exception as e:
        print(f"Error fetching content details: {str(e)}")
        if session and close_session:
            await session.close()
        return None, None

async def get_episodes_data(session, bundle_id, season_num, episode_filter_func=None):
    season_params = {
        "id": f"SONYLIV_VOD_TVSHOW_{bundle_id}_SEASON_{season_num}",
        "appId": "WEB"
    }
    
    data = await get_api_data(session, AIRTEL_API_BASE, DEFAULT_AIRTEL_HEADERS, season_params)
    
    if not data or 'error' in data:
        return None
    
    season_thumbnails = data.get("images", {})
    all_episodes = []
    
    # Collect episodes from all possible sources
    if "tabs" in data:
        for tab in data["tabs"]:
            tab_params = {**season_params, "tab": tab}
            tab_data = await get_api_data(session, AIRTEL_API_BASE, DEFAULT_AIRTEL_HEADERS, tab_params)
            if tab_data and "episodeRefs" in tab_data:
                all_episodes.extend(tab_data["episodeRefs"])
    elif "episodeRefs" in data:
        all_episodes = data["episodeRefs"]
    
    # No filter means return all episodes
    if not episode_filter_func:
        return all_episodes, season_thumbnails
    
    # Find the first episode that matches the filter
    for ep in all_episodes:
        if episode_filter_func(ep):
            # Merge thumbnails, with episode thumbnails taking precedence
            thumbnails = {**season_thumbnails, **(ep.get("images", {}))}
            
            return {
                "content_id": ep["refId"],
                "title": ep.get("name", ""),
                "description": ep.get("description", ""),
                "duration": ep.get("duration", 0),
                "episode_number": ep.get("episodeNumber", 0),
                "season_number": season_num,
                "thumbnails": thumbnails
            }
    
    return None

async def get_episode_details(bundle_id, season, episode, max_seasons=100):
    """Get episode details using Airtel TV API format for SonyLIV shows"""
    try:
        async with aiohttp.ClientSession() as session:
            current_season = season
            
            # Try to find the episode in the specified season and subsequent seasons
            while current_season <= max_seasons:
                episode_filter = lambda ep: ep.get("episodeNumber") == int(episode)
                result = await get_episodes_data(session, bundle_id, current_season, episode_filter)
                
                if result:
                    return result
                
                print(f"Episode {episode} not found in season {current_season}, trying next season...")
                current_season += 1
            
            print(f"Episode {episode} not found in any season up to {max_seasons}")
            return None
                
    except Exception as e:
        print(f"Error fetching episode details: {str(e)}")
        return None

async def find_episode_by_content_id(show_bundle_id, target_content_id, max_seasons=10):
    """Find episode by content ID from show bundle ID by checking all seasons sequentially"""
    try:
        if not show_bundle_id or not target_content_id:
            return None
            
        async with aiohttp.ClientSession() as session:
            # Get seasons info
            params = {"id": f"SONYLIV_VOD_TVSHOW_{show_bundle_id}", "appId": "WEB"}
            data = await get_api_data(session, AIRTEL_API_BASE, DEFAULT_AIRTEL_HEADERS, params)
            
            # Determine season numbers to check
            season_numbers = []
            if data and "seasons" in data:
                season_numbers = [season["seasonNumber"] for season in data["seasons"] 
                                 if "seasonNumber" in season]
            else:
                # If no seasons are specified, check seasons 1 through max_seasons
                season_numbers = list(range(1, max_seasons + 1))
                        
            # Check each season for the episode with matching content ID
            for season_num in season_numbers:
                print(f"Checking season {season_num} for content ID {target_content_id}...")
                episode_filter = lambda ep: extract_numeric_id(ep.get("refId", "")) == target_content_id
                result = await get_episodes_data(session, show_bundle_id, season_num, episode_filter)
                
                if result:
                    return result
        
        print(f"Episode with content ID {target_content_id} not found in any season")
        return None
        
    except Exception as e:
        print(f"Error searching for episode: {str(e)}")
        return None

async def process_sony_url(url, format_choice):
    # Extract content ID from URL
    content_id, is_episode, season, episode, title, show_bundle_id = extract_content_id(url)
    
    if not content_id:
        return {"error": "Could not extract ID from URL"}
    
    # Initialize result structure
    result = {
        "content_url": url,
        "platform": "SonyLIV",
        "title": title or "",
        "content_type": "MOVIE" if not is_episode else "EPISODE",
        "episode_title": None,
        "episode_number": None,
        "year": "",
        "content_id": str(content_id),
        "season": None,
        "episode": None,
        "season_id": None,
        "bundle_id": show_bundle_id,
        "range_id": "",
        "thumbnail": None,
        "subtitles": [],
        "streams": {
            "dash": "",
            "hls": ""
        },
        "drm": {
            "needs_decryption": False,
            "license_url": "",
            "keys": ""
        }
    }
    
    # Process episode details if applicable
    if is_episode:
        episode_details = None
        
        # Handle different types of episode content
        if season and episode:
            # Episode with season and episode numbers
            episode_details = await get_episode_details(content_id, season, episode)
        elif show_bundle_id:
            # Direct episode link with content ID
            episode_details = await find_episode_by_content_id(show_bundle_id, content_id)
        
        if episode_details:
            # Update result with episode details
            result["episode_title"] = episode_details.get('title', '')
            # Get season and episode numbers
            season_num = episode_details.get('season_number', season or 1)
            episode_num = episode_details.get('episode_number', episode or 1) 
            # Format episode_number as "S01E01"
            result["episode_number"] = f"S{season_num:02d}E{episode_num:02d}"
            # Keep the numeric values in separate fields
            result["season"] = season_num
            result["episode"] = episode_num
            
            # Get thumbnail if available
            thumbnails = episode_details.get('thumbnails', {})
            if thumbnails and "LANDSCAPE_169" in thumbnails:
                result["thumbnail"] = thumbnails['LANDSCAPE_169']
            
            # Update content ID
            result["content_id"] = extract_numeric_id(str(episode_details['content_id']))
    
    # Fallback: Get content ID and poster URL directly if needed
    if not result["thumbnail"]:
        async with aiohttp.ClientSession() as session:
            actual_content_id, fallback_poster_url = await get_actual_content_id(result["content_id"], session)
    
            # Update content ID if a more accurate one was found
            if actual_content_id:
                result["content_id"] = str(actual_content_id)
    
            # Use fallback poster URL if no poster URL was set earlier
            if fallback_poster_url:
                result["thumbnail"] = fallback_poster_url
    
    # Extract only numeric part from content ID
    result["content_id"] = extract_numeric_id(result["content_id"])
    
    # Get the specific format requested
    sonyliv = SonyLivFormats()
    selected_format = sonyliv.get_specific_format(result["content_id"], format_choice)
    
    if not selected_format:
        result["error"] = f"Failed to fetch the selected format {format_choice}"
        return result
        
    # Add stream info
    result["streams"]["dash"] = selected_format.get("url", "")
    result["drm"]["license_url"] = selected_format.get("license_url", "")
    result["drm"]["needs_decryption"] = bool(selected_format.get("license_url", ""))
    
    # Process subtitle information from the API response
    try:
        # Extract subtitle information
        subtitle_list = selected_format.get("subtitle_list", [])
        if subtitle_list:
            for sub in subtitle_list:
                subtitle_info = {
                    "language": sub.get("subtitleDisplayName", "Unknown"),
                    "url": sub.get("subtitleUrl", ""),
                    "format": "vtt",  # SonyLIV subtitles are typically in VTT format
                    "languageCode": sub.get("subtitleLanguageName", "").lower(),
                    "subtype": "Normal"
                }
                result["subtitles"].append(subtitle_info)
                
            print(f"Found {len(result['subtitles'])} subtitles")
    except Exception as e:
        print(f"Error extracting subtitles: {str(e)}")
    
    # Extract keys if applicable
    if result["drm"]["needs_decryption"]:
        async with aiohttp.ClientSession() as session:
            mpd_info = await process_mpd_and_keys(selected_format, session)
            
            if mpd_info and mpd_info.get('key'):
                # Store key as a string instead of an array
                result["drm"]["keys"] = mpd_info.get('key', "")
                result["pssh"] = mpd_info.get('pssh', '')
    
    # Add format info
    result["format"] = {
        "name": selected_format.get("dynamic_range", ""),
        "codec": selected_format.get("video_codec", "")
    }
    
    return result

async def process_mpd_and_keys(format_data, session=None):
    """Process MPD content and extract keys"""
    if not format_data:
        return None
        
    mpd_url = format_data.get('url')
    license_url = format_data.get('license_url')
    
    if not mpd_url:
        print("No MPD URL found in format data")
        return None
        
    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True
    
    try:
        # Get MPD content
        mpd_content = None
        try:
            async with session.get(mpd_url, headers=mpd_headers, proxy=proxies['http'] if proxies else None) as response:
                response.raise_for_status()
                mpd_content = await response.text()
        except Exception as e:
            print(f"Error getting MPD content: {str(e)}")
            return None
            
        if not mpd_content:
            print("Failed to retrieve MPD content")
            return None
            
        # Extract PSSH
        pssh_value = None
        if mpd_content:
            root = ET.fromstring(mpd_content)
            ns = {'dash': 'urn:mpeg:dash:schema:mpd:2011',
                  'cenc': 'urn:mpeg:cenc:2013'}
            
            WIDEVINE_SYSTEM_ID = "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"
            
            try:
                for adaptation_set in root.findall('.//dash:AdaptationSet', ns):
                    for content_protection in adaptation_set.findall('.//dash:ContentProtection', ns):
                        scheme_id_uri = content_protection.get('schemeIdUri', '')
                        if WIDEVINE_SYSTEM_ID in scheme_id_uri.lower():
                            pssh_element = content_protection.find('.//cenc:pssh', ns)
                            if pssh_element is not None and pssh_element.text:
                                pssh_value = pssh_element.text.strip()
                                break
                    if pssh_value:
                        break
            except Exception as e:
                print(f"Error parsing MPD: {str(e)}")
        
        if not pssh_value:
            print("No PSSH found in MPD content")
            return {'mpd_url': mpd_url, 'pssh': None, 'key': None}
            
        # Get keys if license URL is available
        key = None
        if license_url and pssh_value:
            try:
                pssh = PSSH(pssh_value)
                device = Device.load("samsung_sm-g935f.wvd")
                cdm = Cdm.from_device(device)
                session_id = cdm.open()
                challenge = cdm.get_license_challenge(session_id, pssh)
                
                headers = {
                    'content-type': 'application/octet-stream',
                    'origin': 'https://www.sonyliv.com',
                    'referer': 'https://www.sonyliv.com/',
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                }
                
                async with session.post(license_url, headers=headers, data=challenge, proxy=proxies['http'] if proxies else None) as response:
                    response.raise_for_status()
                    license_data = await response.read()
                    cdm.parse_license(session_id, license_data)
                    
                    for k in cdm.get_keys(session_id):
                        if k.type == 'CONTENT':
                            key = f"{k.kid.hex}:{k.key.hex()}"
                            break
                    
                    cdm.close(session_id)
            except Exception as e:
                print(f"Error getting keys: {str(e)}")
        
        return {
            'mpd_url': mpd_url,
            'pssh': pssh_value,
            'key': key
        }
    
    finally:
        if close_session and session:
            await session.close()

async def main():
    # Get URL from command line argument
    if len(sys.argv) < 2:
        print("Error: Please provide a SonyLIV URL as command line argument")
        return None
    
    url = sys.argv[1]
    
    # Always use format 4 (NORMAL - H264)
    format_choice = 4
    
    # Process the URL with format 4
    result = await process_sony_url(url, format_choice)
    
    # Print the result as JSON
    print(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    asyncio.run(main())
