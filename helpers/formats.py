

import logging
import asyncio
import sys
import re
from helpers.config import pickFormats, USE_PROXY, PROXY_URL
from hotstar import mpd_hotstar_headers
from sonyliv_api import mpd_headers as get_sonyliv_mpd_headers

logger = logging.getLogger(__name__)

async def get_formats(url, stream_type="dash", max_retries=3):
    try:
        # Get stream URL based on type
        stream_url = url["streams"]["dash"] if stream_type == "dash" and url["streams"].get("dash") else url["streams"].get("hls")
        if not stream_url:
            logger.error("No valid stream URL found")
            return None

        # Get platform and check stream type
        platform = url.get("platform")
        is_hls_stream = "hls" in stream_url or "m3u8" in stream_url
        
        # Define platforms that need N_m3u8DL-RE parser
        nm3u8_platforms = {
            "Crunchyroll": lambda url: True,
            "TataPlay": lambda url: True,
            "JioHotstar": lambda url: not is_hls_stream and not (
                url.startswith("https://hses") and 
                url.split("/")[2].endswith("vod-cf.cdn.hotstar.com")
            ) and not url.startswith("https://ab"),
            "Airtel Xstream": lambda url: not is_hls_stream,
            "Oppai": lambda url: not is_hls_stream
        }
        # Check if current platform needs N_m3u8DL-RE parser
        use_nm3u8 = platform in nm3u8_platforms and nm3u8_platforms[platform](stream_url)
            
        if use_nm3u8:
            result = await get_formats_nm3u8(stream_url, url)
            if result:
                url["formats_from_parser"] = True
                logger.info("Successfully parsed formats with N_m3u8DL-RE")
                return result
            logger.error("Failed to parse formats with N_m3u8DL-RE")
            return None
            
        # Try yt-dlp first for all other platforms
        result = await get_formats_ytdlp(url, stream_url)
        if result:
            return result

        # For ZEE5, if yt-dlp fails, try with modified URL before falling back to N_m3u8DL-RE
        if platform == "ZEE5" and "manifest-connected-4k.mpd" in stream_url:
            logger.info("ZEE5 yt-dlp failed, trying with modified URL")
            # Update the URL in the content info and use it
            if "streams" in url and "dash" in url["streams"]:
                url["streams"]["dash"] = url["streams"]["dash"].replace("manifest-connected-4k.mpd", "manifest.mpd")
                stream_url = url["streams"]["dash"]
            
            result = await get_formats_ytdlp(url, stream_url)
            if result:
                return result

        # Fall back to N_m3u8DL-RE if yt-dlp fails
        logger.info("Falling back to N_m3u8DL-RE")
        result = await get_formats_nm3u8(stream_url, url)
        if result:
            url["formats_from_parser"] = True
            return result

        return None

    except Exception as e:
        logger.exception(f"Error in get_formats: {str(e)}")
        if max_retries > 1:
            logger.info(f"Retrying... Attempt {max_retries - 1}/{max_retries}")
            return await get_formats(url, stream_type, max_retries - 1)
        return None

def is_amazon_audio_duplicate(audio_seen_set, language, bitrate):
    key = (language.lower(), int(bitrate))
    if key in audio_seen_set:
        return True
    audio_seen_set.add(key)
    return False

def get_platform_headers(platform, content_info=None):
    headers_map = {
        "SonyLIV": get_sonyliv_mpd_headers,
        "JioHotstar": mpd_hotstar_headers,
        "ZEE5": {
            "origin": "https://www.zee5.com",
            "referer": "https://www.zee5.com/"
        },
        # SAINAPLAY INTEGRATION
        "SainaPlay": {
            "x-session": content_info.get("session", ""),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Joker/537.36",
            "Referer": "https://sainaplay.com/",
            "Origin": "https://sainaplay.com/"
        },
        # STREAMNXT INTEGRATION
        "Stream NXT": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
    }
    return headers_map.get(platform, {})


def get_platform_proxy(platform):
    proxy_map = {
        "ETV Win": PROXY_URL,
        "ZEE5": PROXY_URL,
        "SonyLIV": PROXY_URL if USE_PROXY else None,
        "JioHotstar": PROXY_URL if USE_PROXY else None,
        "Airtel Xstream": PROXY_URL if USE_PROXY else None,
        "SunNXT": PROXY_URL if USE_PROXY else None
    }
    return proxy_map.get(platform)

def get_lang_name(content_info, lang_code):
    if content_info and content_info.get("platform") in ["Crunchyroll", "JioHotstar"] and content_info.get("selected_language"):
        return content_info["selected_language"]
    base_lang_code = lang_code.split('-')[0] if '-' in lang_code else lang_code
    return pickFormats['audio'].get(base_lang_code, lang_code.upper())

async def get_formats_ytdlp(url, stream_url):
    try:
        yt_dlp_args = ["yt-dlp", "-F", "--allow-unplayable-formats"]
        platform = url.get("platform")
        headers = get_platform_headers(platform, url)  # Pass content_info (url) to get headers
        if headers:
            for header, value in headers.items():
                if value:  # Only add header if value is not empty
                    yt_dlp_args.extend(['--add-header', f'{header}: {value}'])
        if platform in ["Airtel Xstream", "Ullu"] and "cookies" in url:
            yt_dlp_args.extend(['--add-header', f'Cookie: {url["cookies"]}'])
            logger.info(f"Added cookie header for {platform}")
        proxy = get_platform_proxy(platform)
        if proxy:
            yt_dlp_args.append(f"--proxy={proxy}")
            logger.info(f"Using proxy for {platform}: {proxy}")
        yt_dlp_args.append(stream_url)
        logger.info(f"Running command: {' '.join(yt_dlp_args)}")
        process = await asyncio.create_subprocess_exec(
            *yt_dlp_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if stderr:
            stderr_text = stderr.decode().strip()
            if stderr_text and "KeyError('sourceURL')" not in stderr_text:
                 logger.warning(f"yt-dlp stderr: {stderr_text}")
            if "KeyError('sourceURL')" in stderr_text or process.returncode != 0:
                return None
        logger.info(f"\nyt-dlp formats output:\n{stdout.decode()}")
        parsed_streams = {"video": [], "audio": [], "subtitle": []}
        format_lines = stdout.decode().split('\n')
        has_drm = any("DRM" in line for line in format_lines)
        amazon_audio_seen = set() if platform == "Amazon Prime" else None
        for line in format_lines:
            if 'ID' in line or '---' in line or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            format_id = parts[0]
            content_info = url if isinstance(url, dict) else {}
            if (content_info.get("platform") == "SonyLIV" or 
                (content_info.get("platform") == "ZEE5" and format_id.count("_") > 1)):
                format_id = format_id.replace("_", "/")
            if has_drm and "DRM" not in line:
                continue
            if 'audio only' in line:
                audio_stream = parse_audio_format(line, format_id, content_info)
                if audio_stream:
                    if amazon_audio_seen is not None:
                        if is_amazon_audio_duplicate(amazon_audio_seen, audio_stream.get("language", ""), audio_stream.get("bitrate", 0)):
                            continue
                    parsed_streams["audio"].append(audio_stream)
            else:
                video_stream = parse_video_format(line, format_id)
                if video_stream:
                    parsed_streams["video"].append(video_stream)
        for stream_type in ["video", "audio"]:
            parsed_streams[stream_type].sort(key=lambda x: x["bitrate"], reverse=True)
        return {"display": stdout.decode(), "streams": parsed_streams}
    except Exception as e:
        logger.error(f"Error in get_formats_ytdlp: {str(e)}")
        return None

def parse_audio_format(line, format_id, content_info):
    try:
        # Updated regex to capture language codes in square brackets or after MORE INFO
        lang_match = re.search(r'\[([a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?)\]|\[([a-z]{2,3})\]|MORE INFO.*?\[([a-z]{2,3})\]', line)
        lang_code = (lang_match.group(1) or lang_match.group(2) or lang_match.group(3)).lower() if lang_match else 'und'
        lang_name = get_lang_name(content_info, lang_code)
        bitrate_match = re.search(r'(\d+)k', line)
        codec_match = re.search(r'audio only\s+(\S+)', line)
        return {
            "language": lang_name,
            "bitrate": int(bitrate_match.group(1)) if bitrate_match else 0,
            "stream_id": format_id,
            "codec": codec_match.group(1) if codec_match else "unknown"
        }
    except Exception as e:
        logger.error(f"Error parsing audio format: {e}")
        return None

def parse_video_format(line, format_id):
    try:
        res_match = re.search(r'\b(\d+\s*x\s*\d+)\b', line)
        bitrate_match = re.search(r'(\d+)k', line)
        
        if not bitrate_match or 'Extracting' in line:
            return None
            
        bitrate = int(bitrate_match.group(1))
        resolution = res_match.group(1).replace(" ", "") if res_match else get_estimated_resolution(bitrate)
        
        return {
            "resolution": resolution,
            "bitrate": bitrate,
            "stream_id": format_id
        }
    except Exception as e:
        logger.error(f"Error parsing video format: {e}")
        return None

def get_estimated_resolution(bitrate):
    if bitrate <= 500:
        return "480x360"
    elif bitrate <= 800:
        return "640x480"
    elif bitrate <= 1200:
        return "1280x720"
    else:
        return "1920x1080"

async def parse_nm3u8_output(stdout_lines, content_info=None):
    try:
        videos = []
        audios = []
        seen = set()
        amazon_audio_seen = set() if content_info and content_info.get("platform") == "Amazon Prime" else None
        for line in stdout_lines:
            if ('INFO : Vid' in line or 'INFO : Aud' in line):
                if content_info.get("platform") in ["Amazon Prime", "HBO Max"] and '*CENC' not in line:
                    continue
                content = ' '.join(line.split()[3:])
                if content in seen:
                    continue
                seen.add(content)
                if 'INFO : Vid' in line:
                    try:
                        resolution_match = re.search(r'(\d+x\d+)', content)
                        bitrate_match = re.search(r'(\d+)\s*Kbps', content)
                        codec_match = re.search(r'((?:avc1|hev1|hvc1)\.[0-9A-Fa-f.]+)', content)
                        fps_match = re.search(r'\|\s*([\d.]+)\s*\|', content)
                        if resolution_match and bitrate_match:
                            resolution = resolution_match.group(1)
                            bitrate = bitrate_match.group(1)
                            codec = codec_match.group(1) if codec_match else "unknown"
                            fps = fps_match.group(1) if fps_match else "25"
                            parts = content.split('|')
                            if len(parts) > 2:
                                stream_id = parts[2].strip()
                            else:
                                path_match = re.search(r'video_.*?/(?:avc1|hev1|hvc1)/[^|\s]+', content)
                                if not path_match:
                                    path_match = re.search(r'video_[^|\s]+', content)
                                stream_id = path_match.group(0) if path_match else content.split()[0].replace('*CENC', '').strip()
                            videos.append({
                                'resolution': resolution,
                                'bitrate': bitrate,
                                'codec': codec,
                                'fps': fps,
                                'stream_id': stream_id
                            })
                    except Exception as e:
                        print(f"Error parsing video: {str(e)}", file=sys.stderr)
                elif 'INFO : Aud' in line:
                    try:
                        stream_id = content.split('|')[0].replace('*CENC', '').strip()
                        if stream_id.startswith('Aud'):
                            stream_id = stream_id.replace('Aud', '').strip()
                        bitrate_match = re.search(r'(\d+)\s*Kbps', content)
                        codec_match = re.search(r'(mp4a\.[0-9.]+|ec-3)', content)
                        channels_match = re.search(r'(\d+)CH|F801CH', content)
                        lang_match = re.search(r'\|\s*([a-z]{2,3}(?:-[A-Z]{2})?)\s*\|', content)
                        if bitrate_match:
                            bitrate = bitrate_match.group(1)
                            codec = codec_match.group(1) if codec_match else "unknown"
                            channels = channels_match.group(1) if channels_match else "2"
                            language = lang_match.group(1) if lang_match else "unknown"
                            if amazon_audio_seen is not None:
                                if is_amazon_audio_duplicate(amazon_audio_seen, language, bitrate):
                                    continue
                            audios.append({
                                'stream_id': stream_id,
                                'bitrate': bitrate,
                                'codec': codec,
                                'channels': channels,
                                'language': language
                            })
                    except Exception as e:
                        print(f"Error parsing audio: {str(e)}", file=sys.stderr)
        videos.sort(key=lambda x: int(x['bitrate']), reverse=True)
        audios.sort(key=lambda x: int(x['bitrate']), reverse=True)
        parsed_streams = {"video": [], "audio": [], "subtitle": []}
        for video in videos:
            parsed_streams["video"].append({
                "resolution": video['resolution'],
                "bitrate": int(video['bitrate']),
                "stream_id": video['stream_id']
            })
        for audio in audios:
            lang_name = get_lang_name(content_info, audio.get('language', 'unknown').split('-')[0].lower())
            parsed_streams["audio"].append({
                "language": lang_name,
                "bitrate": int(audio['bitrate']),
                "stream_id": audio['stream_id']
            })
        parsed_streams["video"].sort(key=lambda x: x["bitrate"], reverse=True)
        parsed_streams["audio"].sort(key=lambda x: x["bitrate"], reverse=True)
        return parsed_streams
    except Exception as e:
        logger.error(f"Error in parse_nm3u8_output: {str(e)}")
        return None

async def get_formats_nm3u8(stream_url, content_info=None):
    try:
        cmd = ['N_m3u8DL-RE', stream_url, '--skip-download', '--auto-select','--write-meta-json', 'false']
        
        # Add headers for Hotstar
        if content_info and content_info.get("platform") == "JioHotstar":
            headers = mpd_hotstar_headers
            for header, value in headers.items():
                cmd.extend(['-H', f'{header}: {value}'])
        
        # Add language parameter for Hotstar
        if content_info and content_info.get("platform") == "JioHotstar" and content_info.get("language_code"):
            if "?" in stream_url:
                stream_url += f"&lang={content_info['language_code']}"
            else:
                stream_url += f"?lang={content_info['language_code']}"
            logger.info(f"Added language {content_info['language_code']} to stream URL")
            cmd[1] = stream_url  # Update the URL in the command
        
        # Only add proxy if USE_PROXY is True and PROXY_URL is not None
        if USE_PROXY and PROXY_URL:
            cmd.extend(['--custom-proxy', PROXY_URL])
            
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout_lines = []
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            stdout_lines.append(line.decode().strip())
        
        await process.wait()
        
        parsed_streams = await parse_nm3u8_output(stdout_lines, content_info)
        if parsed_streams:
            return {"display": "Using format_parser fallback", "streams": parsed_streams}
        return None

    except Exception as e:
        logger.error(f"Error in get_formats_nm3u8: {str(e)}")
        return None
