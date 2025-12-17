import asyncio
import aiohttp
from urllib.parse import urlparse, parse_qs
from helpers.config import PROXY_URL, DPLUS_ACCESS_TOKEN, USE_PROXY

async def get_playback_info(content_id, headers, session):
    playback_url = 'https://ap2-prod-direct.discoveryplus.in/playback/v3/videoPlaybackInfo'
    
    payload = {
        "deviceInfo": {
            "adBlocker": False,
            "drmSupported": True,
            "hdrCapabilities": ["SDR"],
            "hwDecodingCapabilities": [],
            "player": {"width": 3840, "height": 2160},
            "screen": {"width": 3840, "height": 2160},
            "soundCapabilities": ["STEREO"]
        },
        "videoId": content_id
    }

    try:
        request_kwargs = {'headers': headers, 'json': payload}
        if USE_PROXY:
            request_kwargs['proxy'] = PROXY_URL
            request_kwargs['ssl'] = False
            
        async with session.post(playback_url, **request_kwargs) as response:
            if response.status != 200:
                print(f"Error fetching playback info: HTTP {response.status}")
                return None, None
                
            data = await response.json()
            
            streaming_data = data.get('data', {}).get('attributes', {}).get('streaming', [])
            mpd_url = ''
            m3u8_url = ''
            
            for stream in streaming_data:
                if stream.get('type') == 'dash':
                    mpd_url = stream.get('url', '')
                elif stream.get('type') == 'hls':
                    m3u8_url = stream.get('url', '')
            
            return mpd_url, m3u8_url
    except Exception as e:
        print(f"Error fetching playback info: {e}")
        return None, None

async def get_show_info(url, proxy=None):
    use_proxy = proxy if proxy is not None else (PROXY_URL if USE_PROXY else None)
    
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    
    if 'videos' in path_parts:
        show_id = path_parts[path_parts.index('videos') + 1]
        query_params = parse_qs(parsed_url.query)
        season_num = query_params.get('seasonId', ['1'])[0]
        episode_num = '1'
    elif len(path_parts) > 2:
        if 'mindblown' in path_parts:
            show_id = path_parts[2]
        else:
            show_id = path_parts[1]
            
        if '-' in path_parts[-1]:
            season_episode = path_parts[-1].split('-')
            season_num = season_episode[0]
            episode_num = season_episode[1]
        else:
            print("Invalid URL format")
            return None
    else:
        print("Invalid URL format")
        return None

    headers = {
        'accept': '*/*',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'accept-language': 'en-US,en;q=0.9',
        'origin': 'https://discoveryplus.in',
        'referer': 'https://discoveryplus.in/',
        'sec-ch-ua': '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        'x-disco-client': 'WEB:UNKNOWN:dplus-india:prod',
        'x-disco-params': 'realm=dplusindia,hn=discoveryplus.in',
        'authorization': f'Bearer {DPLUS_ACCESS_TOKEN}'
    }

    try:
        connector = None
        if use_proxy:
            connector = aiohttp.TCPConnector(ssl=False)
            
        async with aiohttp.ClientSession(connector=connector, trust_env=True) as session:
            if use_proxy:
                session._connector._remote_resolve = False
                
            request_kwargs = {'headers': headers}
            if use_proxy:
                request_kwargs['proxy'] = use_proxy
                request_kwargs['ssl'] = False
                
            api_url = f'https://ap2-prod-direct.discoveryplus.in/cms/routes/show/{show_id}'
            params = {
                'include': 'default',
                'decorators': 'isFavorite,viewingHistory'
            }
            request_kwargs['params'] = params

            async with session.get(api_url, **request_kwargs) as response:
                if response.status != 200:
                    print(f"Error fetching show info: HTTP {response.status}")
                    return None
                data = await response.json()
            
            series_id = None
            show_title = ''
            season_id = None
            for item in data.get('included', []):
                if item.get('type') == 'show':
                    series_id = item.get('id')
                    show_title = item.get('attributes', {}).get('name', '')
                elif item.get('type') == 'season' and str(item.get('attributes', {}).get('seasonNumber')) == season_num:
                    season_id = item.get('id')

            if not series_id:
                print("Could not find series ID")
                return None

            episodes_url = 'https://ap2-prod-direct.discoveryplus.in/content/videos'
            episodes_params = {
                'decorators': 'isFavorite',
                'include': 'images,contentPackages,show,genres,primaryChannel,taxonomyNodes',
                'sort': 'episodeNumber',
                'filter[seasonNumber]': season_num,
                'filter[show.id]': series_id,
                'page[size]': 50,
                'page[number]': 1
            }

            request_kwargs = {'headers': headers, 'params': episodes_params}
            if use_proxy:
                request_kwargs['proxy'] = use_proxy

            async with session.get(episodes_url, **request_kwargs) as response:
                episodes_data = await response.json()

            target_episode = None
            for episode in episodes_data.get('data', []):
                if str(episode.get('attributes', {}).get('episodeNumber')) == episode_num:
                    target_episode = episode
                    break

            if target_episode:
                image_url = ''
                if 'relationships' in target_episode and 'images' in target_episode['relationships']:
                    image_ids = target_episode['relationships']['images'].get('data', [])
                    for img_data in episodes_data.get('included', []):
                        if (img_data.get('type') == 'image' and 
                            img_data.get('id') in [img.get('id') for img in image_ids]):
                            image_url = img_data.get('attributes', {}).get('src', '')
                            break

                clean_show_title = show_title.replace('-', '').replace(':', '')
                clean_episode_title = target_episode['attributes']['name'].replace('-', '').replace(':', '')

                mpd_url, m3u8_url = await get_playback_info(target_episode['id'], headers, session)

                info = {
                    "content_url": url,
                    "platform": "Discovery+ India",
                    "title": clean_show_title,
                    "content_type": "EPISODE",
                    "episode_title": clean_episode_title,
                    "episode_number": f"S{int(season_num):02d}E{int(episode_num):02d}",
                    "content_id": target_episode['id'],
                    "thumbnail": image_url,
                    "streams": {
                        "dash": mpd_url,
                        "hls": m3u8_url
                    },
                    "drm": {
                        "needs_decryption": True,
                        "license_url": "",
                        "keys": None
                    }
                }

                print("\nVideo Information")
                print("="*50)
                print(f"Platform: {info['platform']}")
                print(f"Title: {info['title']}")
                print(f"Content Type: {info['content_type']}")
                print(f"Episode Title: {info['episode_title']}")
                print(f"Episode Number: {info['episode_number']}")
                print(f"Content ID: {info['content_id']}")
                print(f"Thumbnail: {info['thumbnail']}")
                
                print("\nStreams:")
                if info['streams']['dash']:
                    print(f"DASH: {info['streams']['dash']}")
                if info['streams']['hls']:
                    print(f"HLS: {info['streams']['hls']}")
                
                return info
            else:
                print(f"Episode {episode_num} not found in season {season_num}")
                return None

    except aiohttp.ClientError as e:
        print(f"Error making API request: {e}")
    except KeyError as e:
        print(f"Error parsing API response: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

async def main():
    url = input("\nEnter Discovery+ URL: ")
    proxy = PROXY_URL if USE_PROXY else None
    if proxy:
        print(f"Using proxy: {proxy}")
    await get_show_info(url, proxy)

if __name__ == "__main__":
    asyncio.run(main())
