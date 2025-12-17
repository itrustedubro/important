import aiohttp
import asyncio
import re
import json
import xml.etree.ElementTree as ET
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import os
from datetime import datetime
import pytz
import logging
# Import proxy configuration from helpers.config
from helpers.config import PROXY_URL, USE_PROXY

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROXY_URL = PROXY_URL
proxies = {
    'http': PROXY_URL,
    'https': PROXY_URL,
} if USE_PROXY else None

class MXPlayer:
    def __init__(self):
        self.base_url = "https://api.mxplayer.in"
        self.license_url = "https://playlicense.mxplay.com/widevine/proxy"
        self.cdm_device_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samsung_sm-g935f.wvd")
        
        self.headers = {
            "authority": "api.mxplayer.in",
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "cookie": "platform=com.mxplay.desktop; UserID=381bd1de-f13a-4975-926c-eff5313dfb29; scrnDPI=1.25; isWebpSupported=1; Content-Languages=en; languageDismissed=saved; scrnWdth=1536",
            "origin": "https://www.mxplayer.in",
            "referer": "https://www.mxplayer.in/",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "Windows",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        
        self.license_headers = {
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.mxplayer.in",
            "referer": "https://www.mxplayer.in/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        
    def extract_video_id(self, url):
        """Extract video ID from MX Player URL"""
        # Try to find the ID at the end of the URL
        video_id = url.split('/')[-1].split('?')[0]
        if len(video_id) == 32:  # MX Player IDs are 32 characters
            return video_id
            
        # If not found, try to find it in the URL path
        pattern = r'([a-f0-9]{32})'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        return None

    def get_content_type(self, url):
        """Determine if the URL is for a movie or episode"""
        if "/show/" in url:
            return "episode"
        return "movie"

    def clean_title(self, title):
        """Clean the title by removing special characters and Hindi Dubbed text"""
        # Remove (Hindi Dubbed) and similar text
        title = re.sub(r'\s*\(?Hindi Dubbed\)?', '', title, flags=re.IGNORECASE)
        # Remove special characters but keep spaces
        title = title.replace(':', ' ').replace('-', ' ')
        # Remove extra spaces
        title = ' '.join(title.split())
        return title

    def get_show_info_from_url(self, url):
        """Extract show title, season and episode from URL"""
        try:
            # Extract show title
            show_match = re.search(r'/watch-(.*?)/season-', url)
            show_title = show_match.group(1) if show_match else None
            if show_title:
                # Remove hindi-dubbed and convert-dashes-to-spaces
                show_title = re.sub(r'-hindi-dubbed', '', show_title, flags=re.IGNORECASE)
                show_title = ' '.join(word.capitalize() for word in show_title.split('-'))
            
            # Extract season number
            season_match = re.search(r'/season-(\d+)/', url)
            season_num = season_match.group(1) if season_match else '1'
            
            # Extract episode number
            episode_match = re.search(r'(?:ep-|episode-)(\d+)', url)
            episode_num = episode_match.group(1) if episode_match else '1'
            
            return {
                'title': show_title,
                'episode_num': f"S{season_num.zfill(2)}E{episode_num.zfill(2)}"
            }
        except:
            return None

    async def get_video_info(self, video_id, original_url):
        """Get video information from MX Player API"""
        content_type = self.get_content_type(original_url)
        
        params = {
            "type": content_type,
            "id": video_id,
            "device-density": "2",
            "userid": "381bd1de-f13a-4975-926c-eff5313dfb29",
            "platform": "com.mxplay.desktop",
            "content-languages": "en",
            "kids-mode-enabled": "false"
        }
        
        url = f"{self.base_url}/v1/web/detail/video"
        
        logger.debug(f"Fetching video info for ID: {video_id} from URL: {url} with params: {params}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params, proxy=proxies['http'] if proxies else None) as response:
                    response.raise_for_status()
                    data = await response.json()

            logger.debug(f"Received data: {data}")

            if not data:
                logger.error("No data received from MX Player API")
                return None

            # Check if required fields exist
            if 'image' not in data or '16x9' not in data['image']:
                logger.error("Invalid data structure - missing image information")
                return None

            # Extract image hash from the 16:9 image URL
            image_16_9 = data['image']['16x9']
            logger.debug(f"Extracted image URL: {image_16_9}")
            
            image_hash = image_16_9.split('/')[-1].split('.')[0]  # Gets "6c30c8a2500f9284c2996f0f0dbf9efe_1920x1080"
            
            # Convert UTC release date to IST
            release_date_utc = data.get('releaseDate')
            release_year = None
            if release_date_utc:
                utc_dt = datetime.strptime(release_date_utc, "%Y-%m-%dT%H:%M:%S.%fZ")
                ist_tz = pytz.timezone('Asia/Kolkata')
                ist_dt = utc_dt.replace(tzinfo=pytz.UTC).astimezone(ist_tz)
                release_year = ist_dt.year
            
            # Get show info from URL for series
            if content_type == "episode":
                show_info = self.get_show_info_from_url(original_url)
                if show_info:
                    cleaned_title = show_info['title']
                    episode_num = show_info['episode_num']
            else:
                cleaned_title = self.clean_title(data.get("title", ""))
                episode_num = None
            
            # For series episodes, get the series poster
            if content_type == "episode":
                series_id = data['container']['container']['id']
                image_hash = data['container']['container']['imageInfo'][0]['url'].split('/')[-1]
                poster_url = f"https://qqcdnpictest.mxplay.com/pic/{series_id}/en/16x9/1920x1080/{image_hash}"
            else:
                # For movies, keep the existing poster logic
                image_hash = data['image']['16x9'].split('/')[-1]
                poster_url = f"https://qqcdnpictest.mxplay.com/pic/{data['id']}/en/16x9/1920x1080/{image_hash}"
            
            # Extract stream URLs with fallback logic
            stream_urls = {
                "dash": None,
                "hls": None
            }
            
            if data['stream'].get('thirdParty'):
                # ThirdParty URL structure
                stream_urls["dash"] = data['stream']['thirdParty'].get('dashUrl')
                stream_urls["hls"] = data['stream']['thirdParty'].get('hlsUrl')
            elif data['stream'].get('dash') and data['stream'].get('hls'):
                # Direct URL structure
                # Try 'high' first, then fall back to 'base' if 'high' is None
                if data['stream']['dash'].get('high'):
                    stream_urls["dash"] = f"https://d3sgzbosmwirao.cloudfront.net/{data['stream']['dash']['high']}"
                elif data['stream']['dash'].get('base'):
                    stream_urls["dash"] = f"https://d3sgzbosmwirao.cloudfront.net/{data['stream']['dash']['base']}"
                
                if data['stream']['hls'].get('high'):
                    stream_urls["hls"] = f"https://d3sgzbosmwirao.cloudfront.net/{data['stream']['hls']['high']}"
                elif data['stream']['hls'].get('base'):
                    stream_urls["hls"] = f"https://d3sgzbosmwirao.cloudfront.net/{data['stream']['hls']['base']}"

            # Extract only needed information
            essential_info = {
                "id": data.get("id"),
                "title": cleaned_title,
                "episode_num": episode_num if content_type == "episode" else None,
                "type": content_type,
                "release_year": release_year,
                "poster": poster_url,
                "stream": stream_urls,
                "drm_protected": data['stream'].get('drmProtect', False),
                "original_url": original_url,
                "video_hash": data['stream'].get('videoHash', '')
            }
            return essential_info

        except aiohttp.ClientError as e:
            logger.error(f"Network error: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return None

    async def extract_pssh(self, mpd_url):
        """Extract PSSH from MPD file"""
        async with aiohttp.ClientSession() as session:
            async with session.get(mpd_url, proxy=proxies['http'] if proxies else None) as response:
                response.raise_for_status()
                content = await response.text()
        
        # Parse MPD XML
        root = ET.fromstring(content)
        
        # Find PSSH in MPD
        # Define XML namespaces
        ns = {
            'cenc': 'urn:mpeg:cenc:2013',
            'dash': 'urn:mpeg:dash:schema:mpd:2011'
        }
        
        # Try to find pssh in different possible locations
        pssh_element = root.find('.//cenc:pssh', ns)
        if pssh_element is not None:
            return pssh_element.text
            
        # If not found in standard location, search in adaptation sets
        for adaptation_set in root.findall('.//dash:AdaptationSet', ns):
            pssh_element = adaptation_set.find('.//cenc:pssh', ns)
            if pssh_element is not None:
                return pssh_element.text
                
        raise Exception("Could not find PSSH in MPD")

    async def get_keys(self, video_info):
        """Get decryption keys using Widevine CDM"""
        try:
            # First check if content is DRM protected from API response
            if not video_info.get('drm_protected', False):
                print("\nKeys : No Keys (DRM Free)")
                return

            # If DRM protected, proceed with key extraction
            pssh_b64 = await self.extract_pssh(video_info['stream']['dash'])
            pssh = PSSH(pssh_b64)
            
            # Load device
            device = Device.load(self.cdm_device_path)
            
            # Initialize CDM
            cdm = Cdm.from_device(device)
            session_id = cdm.open()
            
            # Get license challenge
            challenge = cdm.get_license_challenge(session_id, pssh)
            
            # Send license challenge to MX Player
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.license_url}?content_id={video_info['video_hash']}", 
                    headers=self.license_headers, 
                    data=challenge, 
                    proxy=proxies['http'] if proxies else None
                ) as response:
                    response.raise_for_status()
                    licence_content = await response.read()
            
            # Parse license
            cdm.parse_license(session_id, licence_content)
            
            # Get keys
            print("")  # Add a blank line
            keys = []
            for key in cdm.get_keys(session_id):
                if key.type != "SIGNING":  # Skip the signing key
                    keys.append(f"{key.kid.hex}:{key.key.hex()}")
                
            # Close session
            cdm.close(session_id)
            return keys
            
        except Exception as e:
            print(f"Error getting keys: {str(e)}")
            return None

async def main():
    mx = MXPlayer()
    
    print("\nEnter MX Player URL:")
    url = input().strip()
    logger.debug(f"User entered URL: {url}")
    
    video_id = mx.extract_video_id(url)
    if not video_id:
        logger.error("Could not extract video ID from URL")
        print("Error: Could not extract video ID from URL")
        return
        
    try:
        # Get video info
        info = await mx.get_video_info(video_id, url)
        if info is None:
            logger.error("Could not fetch video information")
            print("Error: Could not fetch video information")
            return
            
        # Get keys if content is DRM protected
        keys = await mx.get_keys(info) if info.get('drm_protected') else None
                
        # Format and print output
        output = f"""Video Information:
--------------------------------------------------
ID: {info['id']}
Title: {info['title']}"""

        # Add Episode No for series/episodes
        if info['type'] == 'episode':
            show_info = mx.get_show_info_from_url(url)
            if show_info and show_info['episode_num']:
                output += f"\nEpisode No: {show_info['episode_num']}"

        output += f"""
Type: {info['type']}
Release Year: {info['release_year']}
Poster: {info['poster']}

M3U8 {info['stream']['hls']}


MPD {info['stream']['dash']}

"""
        if not info.get('drm_protected', False):
            output += "Keys : No Keys (DRM Free)"
        else:
            if keys:
                for key in keys:
                    output += f"Keys : {key}\n"
                    
        print(output)
                
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"\nError: {str(e)}")

async def get_mx_movies(mx_movies=None):
    movies = []
    try:
        # Return empty list if no movies provided
        if not mx_movies:
            print("No movie data provided to get_mx_movies function")
            return []
            
        # Base URL for MX Player posters
        base_poster_url = "https://qqcdnpictest.mxplay.com/pic/"
        
        # Poster format parameters
        poster_params = "/en/16x9/1920x1080/{poster_id}_1920x1080.webp"

        for movie in mx_movies:
            poster_id = movie.get('poster_id', '')
            full_poster_url = f"{base_poster_url}{movie['id']}{poster_params.format(poster_id=poster_id)}" if poster_id else ""
            
            movies.append({
                'title': movie.get('title', ''),
                'thumbnail': full_poster_url,
                'id': movie.get('id', ''),
                'year': movie.get('year', ''),
                'rating': movie.get('rating', ''),
                'plot': movie.get('plot', ''),
                'cast': movie.get('cast', []),
                'genre': movie.get('genre', []),
                'provider': 'mxplayer'
            })
        return movies
    except Exception as e:
        print(f"Error fetching MX Player movies: {e}")
        return []
