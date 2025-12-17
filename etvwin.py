import hashlib
import re
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Optional, Tuple, Any
from urllib.parse import urlparse, parse_qs
# Import proxy configuration from helpers.config
from helpers.config import PROXY_URL, USE_PROXY

# Proxy Configuration
PROXY_URL = PROXY_URL

class ETVWinAPI:
    def __init__(self):
        self.base_url = "https://prod.api.etvwin.com"
        self.auth_token = "q5u8JMWTd2698ncg7q4Q"
        self.access_token = "Ay6KCkajdBzztJ4bptpW"
        self.headers = {
            "authority": "prod.api.etvwin.com",
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.etvwin.com",
            "referer": "https://www.etvwin.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        # Constants for MD5 generation
        self.yn_constant = "f"
        self.country_code = "IN"
        self.session = None
        # Define catalogs that use subcategories for episode access
        self.subcategory_catalogs = ["serials", "win-exclusive"]

    async def create_session(self):
        """Create aiohttp session if not exists"""
        if self.session is None:
            connector = None
            if USE_PROXY:
                connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
            if USE_PROXY:
                self.session.proxy = PROXY_URL
        return self.session

    async def close_session(self):
        """Close aiohttp session if exists"""
        if self.session:
            await self.session.close()
            self.session = None

    def parse_web_url(self, web_url: str) -> tuple:
        parsed = urlparse(web_url)
        path_parts = parsed.path.strip('/').split('/')
        
        # Handle different URL formats
        if len(path_parts) >= 2:
            catalog_type = path_parts[0]
            item_id = path_parts[1]
            
            # For TV shows with episodes, we need to extract the episode ID
            episode_id = None
            season_id = None
            direct_season_num = None
            direct_episode_num = None
            
            if len(path_parts) >= 4:
                # Common format for shows, serials, and win-exclusive: /catalog-type/show-name/season-X/episode-name
                season_id = path_parts[2]
                episode_id = path_parts[3]
                
                # Try to extract episode number directly from URL
                direct_episode_match = re.search(r'epi-(\d+)', episode_id)
                if direct_episode_match:
                    direct_episode_num = direct_episode_match.group(1)
                
                # Try to extract season number directly from URL
                direct_season_match = re.search(r'season-(\d+)', season_id)
                if direct_season_match:
                    direct_season_num = direct_season_match.group(1)
            
            return catalog_type, item_id, season_id, episode_id, direct_season_num, direct_episode_num
        
        return None, None, None, None, None, None

    def generate_ts(self):
        """Generate timestamp like JavaScript: JSON.stringify(Math.floor((new Date).getTime() / 1e3))"""
        current_time_ms = int(datetime.now().timestamp() * 1000)
        seconds = current_time_ms // 1000
        ts = str(seconds)
        return ts

    def generate_md5(self, timestamp):
        """Generate MD5 hash similar to JavaScript: ge().MD5(me.yN + n + a.country_code2).toString()"""
        string_to_hash = self.yn_constant + timestamp + self.country_code
        md5_hash = hashlib.md5(string_to_hash.encode()).hexdigest()
        return md5_hash

    async def get_movie_details(self, url_or_id: str, language: str = "eng", region: str = "IN") -> Optional[Dict]:
        await self.create_session()
        
        if url_or_id.startswith('http'):
            catalog_type, item_id, season_id, episode_id, direct_season_num, direct_episode_num = self.parse_web_url(url_or_id)
            if not catalog_type or not item_id:
                print("Invalid URL format")
                return None
        else:
            catalog_type = "original-movies"
            item_id = url_or_id
            season_id = None
            episode_id = None
            direct_season_num = None
            direct_episode_num = None
        
        # For TV shows or serials, first get the show details
        url = f"{self.base_url}/catalogs/{catalog_type}/items/{item_id}"
        
        params = {
            "auth_token": self.auth_token,
            "access_token": self.access_token,
            "item_language": language,
            "region": region
        }

        try:
            async with self.session.get(url, headers=self.headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                if "data" in data:
                    item_data = data["data"]
                    
                    # Determine content type based on catalog_type
                    content_type = "Movie"
                    if catalog_type and ("tv" in catalog_type.lower() or "show" in catalog_type.lower() or "serial" in catalog_type.lower() or "exclusive" in catalog_type.lower()):
                        content_type = "EPISODE"
                    elif item_data.get('content_type'):
                        if "tv" in item_data.get('content_type', '').lower() or "show" in item_data.get('content_type', '').lower() or "series" in item_data.get('content_type', '').lower():
                            content_type = "EPISODE"
                    
                    # Initialize video info dictionary
                    title = item_data.get('title', 'N/A')
                    # Clean up movie title by removing special characters
                    if content_type == "Movie":
                        title = re.sub(r'\s*\|\s*', ' ', title).strip()
                    
                    video_info = {
                        "content_url": url_or_id,
                        "platform": "ETV Win",
                        "title": title,
                        "content_type": content_type,
                        "episode_title": "",
                        "episode_number": "",
                        "content_id": item_data.get('content_id', 'N/A'),
                        "thumbnail": item_data.get('thumbnails', {}).get('high_16_9', {}).get('url', 'N/A'),
                        "streams": {
                            "dash": "",
                            "hls": ""  # ETV Win uses DASH
                        },
                        "drm": {
                            "needs_decryption": False,  # ETV Win doesn't use DRM
                            "license_url": "",
                            "keys": None
                        }
                    }
                    
                    # For TV shows or serials with episodes, get the episode details
                    if content_type == "EPISODE" and episode_id and season_id:
                        episode_data = None
                        if catalog_type in self.subcategory_catalogs:
                            episode_data = await self.get_subcategory_episode_details(catalog_type, item_id, season_id, episode_id, language, region)
                        else:
                            episode_data = await self.get_episode_details(item_id, episode_id, language, region)
                        
                        if episode_data:
                            # Extract episode number if available
                            episode_title = episode_data.get('title', '')
                            episode_number = ""
                            
                            # Try to extract season and episode numbers from title (e.g., "S24 | Epi 39")
                            season_match = re.search(r'S(\d+)', episode_title)
                            episode_match = re.search(r'Epi\s*(\d+)', episode_title)
                            
                            if season_match and episode_match:
                                season_num = season_match.group(1)
                                epi_num = episode_match.group(1)
                                # Format with leading zeros for single-digit episode numbers
                                episode_number = f"S{int(season_num):02d}E{int(epi_num):02d}"
                            elif episode_match:
                                # Default to S01 when no season number is found
                                epi_num = episode_match.group(1)
                                # Format with leading zeros for single-digit episode numbers
                                episode_number = f"S01E{int(epi_num):02d}"
                            
                            # For serials or win-exclusive, try to extract episode number from friendly_id
                            if catalog_type in self.subcategory_catalogs and not episode_number:
                                epi_match = re.search(r'epi-(\d+)', episode_data.get('friendly_id', ''))
                                if epi_match:
                                    epi_num = epi_match.group(1)
                                    # Format with leading zeros for single-digit episode numbers
                                    episode_number = f"E{int(epi_num):02d}"
                            
                            # If we still don't have an episode number, try using the direct numbers from URL
                            if not episode_number and direct_season_num and direct_episode_num:
                                episode_number = f"S{int(direct_season_num):02d}E{int(direct_episode_num):02d}"
                            elif not episode_number and direct_episode_num:
                                episode_number = f"E{int(direct_episode_num):02d}"
                            
                            # Update video info with episode details
                            video_info.update({
                                "content_id": episode_data.get('content_id', 'N/A'),
                                "episode_title": episode_title,
                                "episode_number": episode_number,
                                "thumbnail": episode_data.get('thumbnails', {}).get('high_16_9', {}).get('url', video_info['thumbnail'])
                            })
                            
                            # Get streaming URL
                            streaming_url = await self.get_streaming_url(
                                video_info["content_id"], 
                                episode_data.get('catalog_id', '')
                            )
                            if streaming_url:
                                video_info["streams"]["dash"] = streaming_url
                    else:
                        # For movies or shows without episodes
                        streaming_url = await self.get_streaming_url(
                            video_info["content_id"], 
                            item_data.get('catalog_id', '')
                        )
                        if streaming_url:
                            video_info["streams"]["dash"] = streaming_url
                    
                    # Print video information
                    print("\nVideo Information:")
                    print("----------------")
                    print(f"Content URL: {video_info['content_url']}")
                    print(f"Platform: {video_info['platform']}")
                    print(f"Title: {video_info['title']}")
                    print(f"Content Type: {video_info['content_type']}")
                    if video_info['episode_title']:
                        print(f"Episode Title: {video_info['episode_title']}")
                    if video_info['episode_number']:
                        print(f"Episode Number: {video_info['episode_number']}")
                    print(f"Content ID: {video_info['content_id']}")
                    print(f"Thumbnail: {video_info['thumbnail']}")
                    print("\nStreams:")
                    print(f"  DASH: {video_info['streams']['dash'] or 'Not available'}")
                    print(f"  HLS: {video_info['streams']['hls'] or 'Not available'}")
                    print("\nDRM Information:")
                    print(f"  Needs Decryption: {video_info['drm']['needs_decryption']}")
                    print(f"  License URL: {video_info['drm']['license_url'] or 'Not available'}")
                    print(f"  Keys: {video_info['drm']['keys'] or 'Not available'}")
                    print("----------------\n")
                    
                    return video_info
                return None
                
        except aiohttp.ClientError as e:
            print(f"Error fetching details: {e}")
            return None

    async def get_episode_details(self, show_id, episode_id, language="eng", region="IN"):
        """Get details for a specific episode of a TV show"""
        await self.create_session()
        
        url = f"{self.base_url}/catalogs/shows/items/{show_id}/episodes/{episode_id}"
        
        params = {
            "auth_token": self.auth_token,
            "access_token": self.access_token,
            "item_language": language,
            "region": region
        }
        
        try:
            async with self.session.get(url, headers=self.headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                if "data" in data:
                    return data["data"]
                return None
                
        except aiohttp.ClientError as e:
            print(f"Error fetching episode details: {e}")
            return None
    
    async def get_subcategory_episode_details(self, catalog_type, item_id, season_id, episode_id, language="eng", region="IN"):
        """Get details for a specific episode that uses subcategories (serials, win-exclusive)"""
        await self.create_session()
        
        url = f"{self.base_url}/catalogs/{catalog_type}/items/{item_id}/subcategories/{season_id}/episodes/{episode_id}"
        
        params = {
            "auth_token": self.auth_token,
            "access_token": self.access_token,
            "item_language": language,
            "region": region
        }
        
        try:
            async with self.session.get(url, headers=self.headers, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                if "data" in data:
                    return data["data"]
                
                # If direct episode fetch fails, try getting related episodes
                related_url = f"{self.base_url}/catalogs/{catalog_type}/items/{item_id}/subcategories/{season_id}/episodes/{episode_id}/related"
                
                async with self.session.get(related_url, headers=self.headers, params=params) as related_response:
                    related_response.raise_for_status()
                    related_data = await related_response.json()
                    
                    if "data" in related_data and "items" in related_data["data"] and len(related_data["data"]["items"]) > 0:
                        # Find the current episode in the related items
                        for item in related_data["data"]["items"]:
                            if item.get("friendly_id") == episode_id:
                                return item
                        
                        # If exact match not found, return the first item
                        return related_data["data"]["items"][0]
                
                return None
                
        except aiohttp.ClientError as e:
            print(f"Error fetching episode details for {catalog_type}: {e}")
            return None
    
    # Maintaining this method for backward compatibility
    async def get_serial_episode_details(self, serial_id, season_id, episode_id, language="eng", region="IN"):
        """Get details for a specific episode of a serial (now handled by get_subcategory_episode_details)"""
        return await self.get_subcategory_episode_details("serials", serial_id, season_id, episode_id, language, region)

    async def get_streaming_url(self, content_id, catalog_id):
        """Get the streaming URL (m3u8) for a specific content"""
        await self.create_session()
        
        # Generate timestamp
        ts = self.generate_ts()
        
        # Generate MD5 hash
        md5_hash = self.generate_md5(ts)
        
        # API endpoint
        url = f"{self.base_url}/v2/users/get_all_details"
        
        # Headers for streaming request
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://www.etvwin.com",
            "referer": "https://www.etvwin.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        }
        
        # Payload data
        payload = {
            "auth_token": self.auth_token,
            "access_token": self.access_token,
            "catalog_id": catalog_id,
            "category": "",
            "content_id": content_id,
            "id": "3aa7e3736170e89adaa8c2d1c8d727ab",
            "md5": md5_hash,
            "region": self.country_code,
            "ts": ts
        }
        
        try:
            # Make the request
            async with self.session.post(url, headers=headers, json=payload) as response:
                # Extract and return only the adaptive m3u8 URL
                if response.status == 200:
                    data = await response.json()
                    adaptive_url = data.get('data', {}).get('stream_info', {}).get('adaptive_url')
                    return adaptive_url
                return None
                
        except aiohttp.ClientError:
            return None

async def main_async():
    api = ETVWinAPI()
    
    print("\nEnter ETVWIN URL:")
    url = input().strip()
        
    if not url.startswith('https://www.etvwin.com/'):
        print("Invalid URL! Please enter a valid ETVWIN URL")
        return
    
    try:
        await api.get_movie_details(url)
    finally:
        await api.close_session()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
