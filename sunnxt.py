import json
from Crypto.Cipher import AES
import base64
import re
import xml.etree.ElementTree as ET
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
import sys
import aiohttp
import asyncio
# Import proxy configuration from helpers.config
from helpers.config import PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD, PROXY_HOST, PROXY_PORT, USE_PROXY

# Use imported proxy configuration
PROXY_USERNAME = PROXY_USERNAME
PROXY_PASSWORD = PROXY_PASSWORD
PROXY_HOST = PROXY_HOST
PROXY_PORT = PROXY_PORT
# Proxy dictionary for requests
PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL
} if USE_PROXY else None

# CDM Configuration
CDM_DEVICE_PATH = "samsung_sm-g935f.wvd"  # Device file in same directory

async def get_keys(pssh_b64, license_url):
    """Get decryption keys using pywidevine"""
    try:
        # prepare pssh
        pssh = PSSH(pssh_b64)
        
        # load device
        device = Device.load(CDM_DEVICE_PATH)
        
        # load cdm
        cdm = Cdm.from_device(device)
        
        # open cdm session
        session_id = cdm.open()
        
        # get license challenge
        challenge = cdm.get_license_challenge(session_id, pssh)
        
        # Headers for license request
        headers = {
            'authority': 'api.sunnxt.com',
            'accept': '*/*',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/octet-stream',
            'origin': 'https://www.sunnxt.com',
            'referer': 'https://www.sunnxt.com/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
        
        try:
            # send license challenge with proxy
            async with aiohttp.ClientSession() as session:
                async with session.post(license_url, headers=headers, data=challenge, proxy=PROXY_URL if USE_PROXY else None) as response:
                    if response.status != 200:
                        print(f"License request failed with status {response.status}")
                        return None
                    
                    licence_content = await response.read()
                    if not licence_content:
                        print("Empty license response received")
                        return None
                    
                    try:
                        # parse license challenge
                        cdm.parse_license(session_id, licence_content)
                    except Exception as parse_error:
                        print(f"Failed to parse license: {str(parse_error)}")
                        return None
                    
                    # get keys
                    keys = {}
                    for key in cdm.get_keys(session_id):
                        # Skip signing key (all zeros)
                        if key.kid.hex != "00000000000000000000000000000000":
                            keys[key.kid.hex] = key.key.hex()
                    
                    # close session
                    cdm.close(session_id)
                    
                    if not keys:
                        print("No valid keys found in license response")
                        return None
                        
                    return keys
                    
        except aiohttp.ClientError as e:
            print(f"Network error during license request: {str(e)}")
            return None
            
    except Exception as e:
        print(f"Error getting keys: {str(e)}")
        return None

async def extract_pssh_from_mpd(mpd_url):
    """Extract PSSH from MPD content"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(mpd_url, proxy=PROXY_URL if USE_PROXY else None) as response:
                if response.status == 200:
                    text = await response.text()
                    # Parse MPD XML
                    root = ET.fromstring(text)
                    # Define XML namespace
                    ns = {'cenc': 'urn:mpeg:cenc:2013',
                         'ns1': 'urn:mpeg:dash:schema:mpd:2011'}
                    
                    # Find pssh in ContentProtection element
                    for elem in root.findall('.//ns1:ContentProtection', ns):
                        pssh = elem.find('.//cenc:pssh', ns)
                        if pssh is not None and pssh.text:
                            return pssh.text
    except Exception as e:
        print(f"Error extracting PSSH: {str(e)}")
    return None

def clean_url(url, extension):
    """Remove parameters from URL after specified extension"""
    if url:
        pattern = f"(.*?{extension})"
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return url

def decrypt_data(encrypted_data, key="A3s68aORSgHs$71P"):
    """Simple decryption with original key"""
    try:
        key_bytes = key.encode('utf-8')[:16]
        decoded = base64.b64decode(encrypted_data)
        iv = b'\0' * 16
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(decoded)
        
        # Try to parse JSON
        cleaned = ''.join(chr(c) if 32 <= c <= 126 else ' ' for c in decrypted)
        json_start = cleaned.find('{')
        json_end = cleaned.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = cleaned[json_start:json_end]
            return json.loads(json_str)
            
    except Exception as e:
        print(f"Decryption error: {str(e)}")
        return {"error": str(e)}

def extract_content_id(url):
    """Extract content ID from SunNXT URL"""
    try:
        # Try to extract comedy content ID
        match = re.search(r'/detail/(\d+)/0$', url)
        if match:
            return match.group(1)
            
        # Try to extract music video content ID
        match = re.search(r'/detail/(\d+)/musicvideo/\d+', url)
        if match:
            return match.group(1)
            
        # Try to extract episode content ID (for TV shows)
        match = re.search(r'/detail/\d+/(\d+)', url)
        if match:
            return match.group(1)
            
        # If not found, try to extract movie content ID
        match = re.search(r'/detail/(\d+)', url)
        if match:
            return match.group(1)
            
    except Exception as e:
        print(f"Error extracting content ID: {str(e)}")
    return None

async def get_sunnxt_data(content_id):
    """Get data from SunNXT API for any content ID"""
    if not content_id:
        return {"error": "Content ID is required"}

    # Get poster URL from pwaapi
    poster_url = None
    pwa_headers = {
        'authority': 'pwaapi.sunnxt.com',
        'accept': '*/*',
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'en-US,en;q=0.9',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    }
    
    pwa_url = f'https://pwaapi.sunnxt.com/content/v3/contentDetail/{content_id}/'
    pwa_params = {
        'level': 'devicemax',
        'fields': 'contents,user/currentdata,images,generalInfo,subtitles,relatedCast,globalServiceName,globalServiceId,relatedMedia,thumbnailSeekPreview,tags,publishingHouse'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(pwa_url, headers=pwa_headers, params=pwa_params, proxy=PROXY_URL if USE_PROXY else None) as pwa_response:
                if pwa_response.status == 200:
                    pwa_data = await pwa_response.json()
                    if isinstance(pwa_data, dict) and 'results' in pwa_data and len(pwa_data['results']) > 0:
                        pwa_result = pwa_data['results'][0]
                        if 'images' in pwa_result and 'values' in pwa_result['images']:
                            for image in pwa_result['images']['values']:
                                if image['type'] == 'coverposter' and image['profile'] == 'xxhdpi':
                                    poster_url = image['link']
                                    break

    except Exception as e:
        print(f"Error getting poster URL: {str(e)}")

    # Original headers and logic for video data
    headers = {
        'authority': 'www.sunnxt.com',
        'accept': '*/*',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'accept-language': 'en-US,en;q=0.9',
        'contentlanguage': 'tamil,telugu,malayalam,kannada,hindi,bengali,marathi,english',
        'cookie': 'sessionid=0y34awb6d9z79h5wzdma9jc62rexlmgf; maturityRestrictions=',
        'priority': 'u=1, i',
        'referer': f'https://www.sunnxt.com/live/content/{content_id}',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'x-myplex-maturity-level': '',
        'x-myplex-platform': 'browser'
    }
    
    url = f'https://www.sunnxt.com/next/api/media/{content_id}'
    params = {
        'playbackCounter': '1',
        'fields': 'contents,user/currentdata,images,generalInfo,subtitles,relatedCast,globalServiceName,globalServiceId,relatedMedia,videos,thumbnailSeekPreview',
        'licenseType': 'false'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, proxy=PROXY_URL if USE_PROXY else None) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict) and 'response' in data:
                        decrypted_data = decrypt_data(data['response'])
                        
                        if decrypted_data and 'results' in decrypted_data and len(decrypted_data['results']) > 0:
                            result = decrypted_data['results'][0]
                            
                            # Find MPD and M3U8 URLs
                            mpd_data = None
                            m3u8_url = None
                            pssh = None
                            keys = None
                            
                            if 'videos' in result and 'values' in result['videos']:
                                for video in result['videos']['values']:
                                    if video['format'] == 'dash-cenc':
                                        # Get full MPD URL for PSSH extraction
                                        mpd_url = video['link']
                                        pssh = await extract_pssh_from_mpd(mpd_url)
                                        
                                        if pssh:
                                            keys = await get_keys(pssh, video['licenseUrl'])
                                        
                                        mpd_data = {
                                            'url': clean_url(mpd_url, '.mpd'),
                                            'license': video['licenseUrl']
                                        }
                                    elif video['format'] == 'hls-fp-aapl':
                                        m3u8_url = clean_url(video['link'], '.m3u8')
                            
                            # Format response
                            response_data = {
                                "channel": "https://t.me/ToonsUniverseOfficial",
                                "data": [
                                    {
                                        "id": result['_id'],
                                        "title": result['generalInfo']['title'].replace(" - ", "  ").replace(", ", "  ") if " - " in result['generalInfo']['title'] else result['generalInfo']['title'].replace(", ", "  "),
                                        "stream_type": result['generalInfo']['type'],
                                        "poster": poster_url,
                                        "m3u8": m3u8_url,
                                        "mpd": mpd_data['url'] if mpd_data else None,
                                        "keys": f"{next(iter(keys.items()))[0]}:{next(iter(keys.items()))[1]}" if keys else None,
                                        "license": mpd_data['license'] if mpd_data else None
                                    }
                                ]
                            }
                            return response_data
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Failed to get content data"}

async def main():
    # Get URL from user input
    url = input("Enter SUNNXT URL: ").strip()
    
    # Extract content ID from URL
    content_id = extract_content_id(url)
    if not content_id:
        print("Error: Could not extract content ID from URL")
        sys.exit(1)

    # Get content data
    result = await get_sunnxt_data(content_id)
    
    # Print formatted output
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
        
    data = result["data"][0]
    print("\nSunNXT Stream Information:")
    print("-" * 50)
    print(f"Title: {data['title']}")
    print(f"Content ID: {data['id']}")
    print(f"Stream Type: {data['stream_type']}")
    if data['poster']:
        print(f"Poster: {data['poster']}")
    print("\nStream URLs:")
    if data['m3u8']:
        print(f"HLS: {data['m3u8']}")
    if data['mpd'] and data['keys']:
        print(f"\nMPD: {data['mpd']}")
        print(f"KEY: {data['keys']}")

if __name__ == '__main__':
    asyncio.run(main())
