import re
import asyncio
import aiohttp
import logging
import time
from datetime import datetime
import json
from helpers.config import get_language_name
from helpers.formats import get_formats, get_formats_nm3u8, get_formats_ytdlp
#OTT Platforms Imports
from pyrogram import filters

import dplus  # Add Discovery+ import

from mxplayer import MXPlayer

from sonyliv_api import process_sony_url

from sunnxt import (
    extract_content_id as extract_sunnxt_content_id,
    get_sunnxt_data,
)


# Setup logger
logger = logging.getLogger(__name__)

async def handle_dplus(client, message, url):
    """
    Handle Discovery+ India URLs by fetching content info and returning structured data
    """    
    # Only process Discovery+ URLs
    if not url.startswith(("https://www.discoveryplus.in", "https://discoveryplus.in")):
        logger.error(f"Invalid Discovery+ URL format: {url}")
        return None   

    async def dplus_task():
        try:
            # Call the Discovery+ fetch function with proxy configuration
            logger.info(f"Fetching Discovery+ show info for URL: {url}")
            # Use the proxy configuration from dplus module
            proxy = dplus.PROXY_URL if dplus.USE_PROXY else None
            result_info = await dplus.get_show_info(url, proxy=proxy)
            
            if not result_info:
                logger.error("Discovery+ API returned no data")
                await message.reply("❌ Failed to fetch content information from Discovery+. Please check if the URL is valid.")
                return None
                         
            # Create standardized info object
            info = {
                "content_url": result_info["content_url"],
                "platform": result_info["platform"],
                "title": result_info["title"],
                "content_type": result_info["content_type"],
                "episode_title": result_info["episode_title"],
                "episode_number": result_info["episode_number"],
                "content_id": result_info["content_id"],
                "thumbnail": result_info["thumbnail"],
                "streams": {
                    "dash": result_info["streams"]["dash"],
                    "hls": result_info["streams"]["hls"]
                },
                "drm": {
                    "needs_decryption": result_info["drm"]["needs_decryption"],
                    "license_url": result_info["drm"]["license_url"],
                    "keys": result_info["drm"]["keys"]
                }
            }
            
            # Get formats information
            logger.info("Fetching format information for Discovery+")
            formats = await get_formats(info)
            if formats:
                info["streams_info"] = formats["streams"]
                logger.info("Successfully retrieved format information")
            else:
                logger.warning("Failed to retrieve format information for Discovery+")
                await message.reply("⚠️ Failed to get video format information. The content might be unavailable.")
                return None
                
            logger.info("Successfully processed Discovery+ URL and returning info")
            return info
            
        except KeyError as e:
            logger.error(f"Missing required field in Discovery+ response: {str(e)}")
            await message.reply(f"❌ Error: Invalid response format from Discovery+")
            return None
        except Exception as e:
            logger.error(f"Discovery+ error: {str(e)}", exc_info=True)
            await message.reply(f"❌ Error processing Discovery+ content: {str(e)}")
            return None
    
    # Create task for Discovery+ processing
    task = asyncio.create_task(dplus_task())  # Create task immediately
    return task  # Return the created task

async def handle_sonyliv(client, message, url):
    """Handle SonyLIV URL and return content information."""
    if not url.startswith(("https://www.sonyliv.com", "https://sonyliv.com")):
        return None

    async def sonyliv_task():
        try:
            # Always auto-select NORMAL (H264) format
            format_choice = 4
            
            # Process URL using sonyliv_api functions with the selected format
            result = await process_sony_url(url, format_choice)
            if not result:
                logger.error(f"Failed to get content info for URL: {url}")
                return None

            # Get formats information
            formats = await get_formats(result)
            if formats:
                result["streams_info"] = formats["streams"]
                logger.info("Successfully retrieved format information")
            else:
                logger.warning("Failed to retrieve format information")

            logger.info("Successfully processed SonyLIV URL and returning info")
            return result

        except Exception as e:
            logger.error(f"Error in handle_sonyliv: {str(e)}")
            return None

    task = asyncio.create_task(sonyliv_task())  # Create task immediately after URL check
    return task

async def handle_disneyplus(client, message, url):
    """Handle DisneyPlus URL and return content information."""
    if not url.startswith(("https://www.disneyplus.com", "https://disneyplus.com")):
        return None

    async def disneyplus_task():
        try:
            # Call the DisneyPlus main function
            result = await disney.main(url)
            
            if not result or "error" in result:
                logger.error(f"Failed to get DisneyPlus content info: {result.get('error', 'Unknown error')}")
                return None

            # Map DisneyPlus result to standardized info structure
            info = {
                "content_url": url,
                "platform": "DisneyPlus",
                "title": result["metadata"]["title"],
                "content_type": "EPISODE" if result["type"] == "episode" else "MOVIE",
                "episode_title": result["metadata"].get("episode_title"),
                "episode_number": result["metadata"].get("episode_number"),
                "content_id": result["metadata"]["entity_id"],
                "thumbnail": result["metadata"].get("landscape_image") or result["metadata"].get("poster"),
                "streams": {
                    "dash": result.get("streaming", {}).get("url"),
                    "hls": None  # DisneyPlus uses DASH
                },
                "drm": {
                    "needs_decryption": True,  # DisneyPlus content is always encrypted
                    "license_url": None,  # DisneyPlus uses a different DRM system
                    "keys": ",".join(result.get("streaming", {}).get("keys", "")) if result.get("streaming", {}).get("keys") else "",
                    "pssh": result.get("streaming", {}).get("pssh")
                }
            }

            # Get formats information
            formats = await get_formats(info)
            if formats:
                info["streams_info"] = formats["streams"]
                logger.info("Successfully retrieved DisneyPlus format information")
            else:
                logger.warning("Failed to retrieve format information for DisneyPlus")
                return None

            return info

        except Exception as e:
            logger.error(f"Error in handle_disneyplus: {str(e)}")
            return None

    return await disneyplus_task()



async def handle_etvwin(client, message, url):
    """Handle ETV Win URL and return content information."""
    if not url.startswith(("https://www.etvwin.com", "https://etvwin.com")):
        return None

    async def etvwin_task():
        try:
            api = ETVWinAPI()
            
            try:
                # Get video details directly using get_movie_details
                info = await api.get_movie_details(url)
                
                if not info:
                    logger.error("Failed to fetch ETV Win content details")
                    return None

                # Get formats information
                formats = await get_formats(info)
                if formats:
                    info["streams_info"] = formats["streams"]
                    logger.info("Successfully retrieved ETV Win format information")
                else:
                    logger.warning("Failed to retrieve ETV Win format information")

                return info

            finally:
                await api.close_session()

        except Exception as e:
            logger.exception(f"Error in handle_etvwin: {str(e)}")
            return None

    return await etvwin_task()















async def handle_sunnxt(client, message, url):
    """Handle SunNXT URL and return content information."""
    if not url.startswith(("https://www.sunnxt.com", "https://sunnxt.com")):
        return None

    async def sunnxt_task():
        try:
            # Extract content ID
            content_id = extract_sunnxt_content_id(url)
            if not content_id:
                logger.warning("Failed to extract content ID")
                return None
                
            # Get content details
            content_data = await get_sunnxt_data(content_id)
            if not content_data or "error" in content_data:
                logger.warning("Failed to get content details")
                return None

            # Get the first item from data array
            data = content_data["data"][0]

            info = {
                "content_url": url,
                "platform": "SunNXT",
                "title": data.get('title', ''),
                "content_type": "EPISODE" if "episode" in data.get('stream_type', '').lower() else "MOVIE",
                "episode_title": None,
                "episode_number": None,
                "year": "",  # SunNXT doesn't provide year info
                "content_id": data.get('id', ''),
                "thumbnail": data.get('poster', ''),
                "streams": {
                    "dash": data.get('mpd', ''),
                    "hls": data.get('m3u8', '')
                },
                "drm": {
                    "needs_decryption": bool(data.get('keys')),
                    "license_url": data.get('license', ''),
                    "keys": data.get('keys')
                }
            }

            # Get formats information
            formats = await get_formats(info)
            if formats:
                info["streams_info"] = formats["streams"]
                logger.info("Successfully retrieved format information")
            else:
                logger.warning("Failed to retrieve format information")

            return info

        except Exception as e:
            logger.exception(f"Error in handle_sunnxt: {str(e)}")
            return None

    task = asyncio.create_task(sunnxt_task())  # Create task immediately after URL check
    return task  # Return the created task

async def handle_chaupal(client, message, url):
    """Handle ChaupalTV URL and return content information."""
    if not url.startswith(("https://www.chaupal.tv", "https://chaupal.tv")):
        return None

    async def chaupal_task():
        try:
            # Check if it's a series episode URL with season-episode format
            series_match = re.search(r'/tv-show/[^/]+/([a-f0-9-]+)/(\d+)-(\d+)$', url)
            if series_match:
                series_id = series_match.group(1)
                season_num = int(series_match.group(2))
                episode_num = int(series_match.group(3))
                
                logger.info(f"Detected series URL - ID: {series_id}, Season: {season_num}, Episode: {episode_num}")
                
                # Get series data
                series_data = fetch_chaupal_data(series_id)
                if not series_data:
                    logger.warning("Failed to get series data")
                    return None
                
                # Find the correct season
                seasons = [child for child in series_data.get('children', []) if child.get('type') == 'SEASON']
                logger.info(f"Found {len(seasons)} seasons")
                
                target_season = None
                for season in seasons:
                    if season.get('order') == season_num:
                        target_season = season
                        break
                
                if not target_season:
                    logger.warning(f"Could not find Season {season_num}")
                    return None
                
                # Find the target episode
                target_episode = None
                episodes = target_season.get('children', [])
                logger.info(f"Found {len(episodes)} episodes in season {season_num}")
                
                for episode in episodes:
                    if episode.get('type') == 'EPISODE' and episode.get('order') == episode_num:
                        target_episode = episode
                        break
                
                if not target_episode:
                    logger.warning(f"Could not find S{season_num}E{episode_num}")
                    return None
                
                # Get episode data
                content_data = fetch_chaupal_data(target_episode['id'])
                if not content_data:
                    logger.warning("Failed to get episode details")
                    return None
                
                # Get bundle ID and content ID for playback
                bundle_id = target_episode['id']  # Use episode ID as bundle ID
                
                # Get content ID from MAIN content or fallback to id
                contents = content_data.get('contents', [])
                main_content = next((content for content in contents if content.get('type') == 'MAIN'), None)
                content_id = main_content.get('slug') if main_content else content_data.get('id')
                
                if not content_id:
                    logger.warning("Could not determine content ID")
                    return None
                
                logger.info(f"Using bundle_id: {bundle_id}, content_id: {content_id}")

            else:
                # Regular movie/show URL handling
                content_id = extract_chaupal_id_from_url(url)
                if not content_id:
                    logger.warning("Failed to extract content ID")
                    return None
                
                content_data = fetch_chaupal_data(content_id)
                if not content_data:
                    logger.warning("Failed to get content details")
                    return None

                # Get bundle ID and content ID for playback
                bundle_id = content_data.get('id')
                contents = content_data.get('contents', [])
                main_content = next((c for c in contents if c.get('type') == 'MAIN'), None)
                content_id = main_content.get('slug') if main_content else content_data.get('id')

                if not bundle_id or not content_id:
                    logger.warning("Missing bundle ID or content ID")
                    return None

            # Get playback data - don't overwrite bundle_id and content_id here
            playback_data = fetch_chaupal_playback_data(bundle_id, content_id)
            if not playback_data or not playback_data[0]:
                logger.warning("Failed to get playback data")
                return None

            mpd_url = playback_data[0].get('url')
            license_url = playback_data[0].get('licenseUrl')

            # Extract PSSH and get keys
            pssh = extract_chaupal_pssh_from_mpd(mpd_url)
            keys = get_chaupal_keys(pssh, license_url) if pssh else None

            info = {
                "content_url": url,
                "platform": "ChaupalTV",
                "title": content_data.get('name', ''),
                "content_type": "EPISODE" if content_data.get('type') == 'EPISODE' else "MOVIE",
                "episode_title": None,
                "episode_number": None,
                "year": "",  # ChaupalTV doesn't provide year info
                "content_id": content_id,
                "thumbnail": next((img['url'] for img in content_data.get('images', []) 
                                 if img['type'] == 'thumbnail'), ''),
                "streams": {
                    "dash": mpd_url,
                    "hls": ""  # ChaupalTV uses DASH
                },
                "drm": {
                    "needs_decryption": True,
                    "license_url": license_url,
                    "keys": keys[0] if keys else None
                }
            }

            # Handle episode info if it's a TV show
            if info["content_type"] == "EPISODE":
                if series_match:
                    # For direct season-episode URLs
                    info["episode_number"] = f"S{season_num:02d}E{episode_num:02d}"
                    info["episode_title"] = content_data.get('name')
                    info["title"] = series_data.get('name', '')
                    # Use series thumbnail for better consistency
                    series_thumbnail = next((img['url'] for img in series_data.get('images', []) 
                                          if img['type'] == 'thumbnail'), info["thumbnail"])
                    info["thumbnail"] = series_thumbnail
                else:
                    # For regular episode URLs
                    parent_id = content_data.get('rootId')
                    season_order = content_data.get('parentId')
                    if parent_id:
                        show_data = fetch_chaupal_data(parent_id)
                        if show_data:
                            season = next((s for s in show_data.get('children', []) 
                                         if s.get('id') == season_order), None)
                            if season:
                                info["episode_number"] = f"S{season.get('order', 1):02d}E{content_data.get('order', 1):02d}"
                                info["episode_title"] = content_data.get('name')
                                info["title"] = show_data.get('name', '')

            # Get formats information
            formats = await get_formats(info)
            if formats:
                info["streams_info"] = formats["streams"]
                logger.info("Successfully retrieved format information")
            else:
                logger.warning("Failed to retrieve format information")

            return info

        except Exception as e:
            logger.exception(f"Error in handle_chaupal: {str(e)}")
            return None

    task = asyncio.create_task(chaupal_task())  # Create task immediately after URL check
    return task  # Return the created task

async def handle_mxplayer(client, message, url):
    """Handle MXPlayer URL and return content information."""
    if not url.startswith(("https://www.mxplayer.in", "https://mxplayer.in")):
        return None

    async def mxplayer_task():
        try:
            # Initialize MXPlayer
            mx = MXPlayer()
            
            # Extract video ID
            video_id = mx.extract_video_id(url)
            if not video_id:
                logger.warning("Failed to extract video ID")
                return None
                
            # Get video information
            video_info = await mx.get_video_info(video_id, url)
            if not video_info:
                logger.warning("Failed to get video information")
                return None
                
            # Get DRM keys if content is protected
            keys = None
            if video_info.get('drm_protected'):
                keys = await mx.get_keys(video_info)
                
            info = {
                "content_url": url,  # Store the original URL
                "platform": "MXPlayer",
                "title": video_info.get("title", "") if video_info.get("type") == "movie" else video_info.get("title", ""),
                "content_type": "EPISODE" if video_info.get("type") == "episode" else "MOVIE", 
                "episode_title": None,
                "episode_number": video_info.get("episode_num") if video_info.get("type") == "episode" else None,
                "year": str(video_info.get("release_year", "")),
                "content_id": video_info.get("id", ""),
                "thumbnail": video_info.get("poster", ""),
                "streams": {
                    "hls": video_info["stream"].get("hls", ""),
                    "dash": video_info["stream"].get("dash", "")
                },
                "drm": {
                    "needs_decryption": video_info.get("drm_protected", False),
                    "license_url": "https://playlicense.mxplay.com/widevine/proxy",
                    "keys": keys
                }
            }
            
            # Get formats information
            formats = await get_formats(info)
            if formats:
                info["streams_info"] = formats["streams"]
                logger.info("Successfully retrieved format information")
            else:
                logger.warning("Failed to retrieve format information")
                
            return info
                
        except Exception as e:
            logger.exception(f"Error in handle_mxplayer: {str(e)}")
            return None

    task = asyncio.create_task(mxplayer_task())  # Create task immediately after URL check
    return task  # Return the created task

async def handle_zee(client, message, url):
    """Handle ZEE5 URL and return content information."""
    if not url.startswith(("https://www.zee5.com", "https://zee5.com")):
        return None

    try:
        # Import the process_url function
        from zee_api import process_url
        
        # Get content info using process_url
        result = await process_url(url)
        
        if not result or result.get("status") != "success":
            return None
            
        # Check if it's a movie based on URL or missing/empty episode title
        episode_title = result.get("episode_title", "")
        is_movie = "movie" in url.lower() or "movies" in url.lower() or not episode_title or episode_title.strip() == ""
            
        # Map to required format
        info = {
            "content_url": url,
            "platform": "ZEE5", 
            "title": result.get("title", ""),
            "episode_title": result.get("episode_title", ""),
            "episode_number": "" if is_movie else result.get("episode_number", ""),
            "content_type": "MOVIE" if is_movie else "EPISODE",
            "content_id": result.get("content_id", ""),
            "thumbnail": result.get("thumbnail", ""),
            "streams": {
                "hls": result.get("streams", {}).get("hls", ""),
                "dash": result.get("streams", {}).get("dash", "")
            },
            "drm": {
                "needs_decryption": result.get("drm", {}).get("needs_decryption", True),
                "license_url": "https://spapi.zee5.com/widevine/getLicense",
                "keys": result.get("drm", {}).get("keys")
            }
        }
        
        # Get formats information
        formats = await get_formats(info)
        if formats:
            info["streams_info"] = formats["streams"]
            logger.info("Successfully retrieved format information")
        else:
            logger.warning("Failed to retrieve format information")
            
        return info
        
    except Exception as e:
        logger.error(f"Error in handle_zee: {str(e)}")
        return None

