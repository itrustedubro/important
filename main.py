
# Standard library imports
import functools
import os, shutil, asyncio, json, logging, time, threading, re, signal
from datetime import datetime, timedelta

# Third party imports
import uvloop  # type: ignore
import aiohttp, aiofiles
import motor.motor_asyncio  # For MongoDB support
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import MessageNotModified, FloodWait
from pyrogram.enums import ChatMemberStatus
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
import requests as sync_requests
import base64 as sync_base64
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH

# Local imports
#import mediainfo
from sub import ttml_to_srt, vtt_to_srt
# from helpers.status import send_status_update # This will be implemented directly
from helpers.session import PremiumSessionPool
from helpers.utils import (
    cleanup_old_files, get_available_drive,
    get_isolated_download_path, store_content_info, cleanup_download_dir,
    get_drive_config
)
from helpers.download import (
    YTDLPDownloader, Nm3u8DLREDownloader,
    QBitDownloader,
    periodic_dump_cleanup
)
from helpers.config import (
    MP4_USER_IDS, USE_PROXY, PROXY_URL,
    pickFormats, get_iso_639_2
)
from helpers.formats import get_formats

from helpers.handlers import (
    handle_zee, handle_mxplayer, handle_aha, handle_sunnxt,
    handle_dplus, handle_sonyliv
)

# OTT Platform imports
import amzn
import hotstar

# Initialize uvloop
uvloop.install()

# Amazon Prime Video settings
USE_AMAZON_API_ENDPOINT = False  # Use Flask API endpoint instead of direct function calls
USE_AMAZON_264 = False  # Use 264 format (False for 265)
AMAZON_API_ENDPOINT = "http://143.244.136.79:7654"  # API endpoint base URL
AMAZON_CODEC_SELECTOR = True  # Set to False to bypass codec selection menu and use default option 1

# Logging configuration
class SuppressSSLShutdownTimeout(logging.Filter):
    def filter(self, record):
        msg = str(record.getMessage())
        return "Error while closing connector: ClientConnectionError('Connection lost: SSL shutdown timed out'" not in msg

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'bot_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.addFilter(SuppressSSLShutdownTimeout())

# Disable non-critical logging
logging.getLogger("pyrogram").setLevel(logging.CRITICAL)
logging.getLogger("pyrogram.session.session").setLevel(logging.CRITICAL)
logging.getLogger("pyrogram.connection.connection").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("http.client").setLevel(logging.WARNING)

# Bot configuration
API_ID = 7041911
API_HASH = "abab2561c71e3004a55d4ff9763d5383"
BOT_TOKEN = "7948031954:AAG1Mqvbsd3dkJ5vt0hLowm1uU9KSXCEmWA"
PREMIUM_STRING = ""
ASSISTANT_BOT = "payer_17"
ALLOWED_ID = [-1002796491419, -1003031974467, 1894915577]
# MongoDB Configuration
MONGO_DB_URI = "mongodb+srv://auto2:auto2@cluster0.fconnog.mongodb.net/?appName=Cluster0"
DB_NAME = "OTT_BOT"

# Initialize MongoDB client
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DB_URI)
db = mongo_client[DB_NAME]
thumb_db = db["thumbnails"]

# Channel configuration
OWNER_CHANNEL = "addafilez"
OWNER = "@payer_17"
#MAIN_CHANNEL = -1002705260914
METASUFFIX = "addafilez"

# Initialize bot client
app = Client(
    name="ooott",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    max_concurrent_transmissions=20
)

# Platform examples and configurations
PLATFORM_EXAMPLES = {
    "-zee": ["ZEE5", "https://www.zee5.com/movies/details/xxx/1234567890"],
    "-sony": ["SonyLIV", "https://www.sonyliv.com/shows/xxx/1234567890"],
    "-sunxt": ["SunNXT", "https://www.sunnxt.com/detail/123456"],
    "-jstar": ["JioHotstar", "https://www.hotstar.com/movies/xxx/1234567890"],
    "-mxp": ["MXPlayer", "https://www.mxplayer.in/movie/watch-movie-name-online-video_id"],
    "-aha": ["Aha", "https://www.aha.video/movie/xxx"],
    "-amzn": ["Amazon Prime", "https://www.primevideo.com/detail/xxx/1234567890"],
    "-dplus": ["Discovery+", "https://www.discoveryplus.in/shows/xxx/1-1"],
}

# Platform suffixes for output filenames
PLATFORM_SUFFIXES = {
    "ZEE5": "ZEE5",
    "MXPlayer": "MX",
    "Aha": "AHA",
    "SunNXT": "SNXT",
    "SonyLIV": "SONY",
    "JioHotstar": "JIOHS",
    "Amazon Prime": "AMZN",
    "Discovery+ India": "DSCV+",
}

# Trial restricted platforms
TRIAL_RESTRICTED_PLATFORMS = {
    "ZEE5": "ZEE5 is not available in trial mode",
    "MXPlayer": "MXPlayer is not available in trial mode",
    "Aha": "Aha is not available in trial mode",
    "SunNXT": "SunNXT is not available in trial mode",
    "SonyLIV": "SonyLIV is not available in trial mode",
    "JioHotstar": "Hotstar is not available in trial mode",
    "Amazon Prime": "Amazon Prime is not available in trial mode",
    "Discovery+ India": "Discovery+ India is not available in trial mode",
}

# Load premium users from premium referrals JSON
async def get_premium_users_async():
    try:
        async with aiofiles.open('data/premium_referrals.json', 'r') as f:
            content = await f.read()
            premium_data = await asyncio.to_thread(json.loads, content)
            return set(map(int, premium_data.keys()))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def get_premium_users():
    """Get premium users synchronously"""
    try:
        with open('data/premium_referrals.json', 'r') as f:
            premium_data = json.load(f)
            return set(map(int, premium_data.keys()))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

# Base full access users
BASE_FULL_ACCESS = {1894915577, 7361945688}

OWNERS = {1894915577, 7361945688}
# Users with special platform access
TATAPLAY_USER = {7815873054, 7361945688, 7172796863, 822802868, 1291393407}  # Users allowed to access TataPlay

def get_full_access_users():
    """Get all users with full access by combining base users and premium users"""
    return BASE_FULL_ACCESS | get_premium_users()

MP4_USER_IDS = {"5833114414"}  # User IDs that get mp4 extension instead of mkv


# Update premium users periodically
def update_premium_users():
    global BASE_FULL_ACCESS
    premium_users = get_premium_users()
    BASE_FULL_ACCESS = BASE_FULL_ACCESS | premium_users

# Add these new variables for trial access
TRIAL_ACCESS = {}  # Trial access group ID directly as a set
TRIAL_COOLDOWNS = {}  # Store user cooldowns
TRIAL_COOLDOWN_SUCCESS = 15 * 60  # 15 minutes in seconds
TRIAL_COOLDOWN_FAIL = 3 * 60  # 3 minutes in seconds

# Add this after other global variables
MAIN_CHANNEL = -1002705260914  # Main channel ID

MAX_DOWNLOAD_RETRIES = 2

# Add semaphore for controlling concurrent downloads/uploads
download_semaphore = asyncio.Semaphore(10)  # Allow 10 concurrent downloads
upload_semaphore = asyncio.Semaphore(10)  # Allow 10 concurrent uploads

# Lock state file
LOCK_FILE = 'data/bot_lock.json'

MEMORY_LOCKED = False  # In-memory lock for /block -x

def is_bot_locked():
    return MEMORY_LOCKED or _is_file_locked()

def _is_file_locked():
    try:
        with open(LOCK_FILE, 'r') as f:
            data = json.load(f)
            return data.get('locked', False)
    except (FileNotFoundError, json.JSONDecodeError):
        return False

def set_bot_lock(state: bool):
    os.makedirs('data', exist_ok=True)
    with open(LOCK_FILE, 'w') as f:
        json.dump({'locked': state}, f)

LOCK_MESSAGE = (
    "🚫 **Bot is temporarily locked by admin.**\n\n"
    "This action is taken for maintenance, restart, or testing.\n"
    "Please wait a few minutes. If this takes too long, contact the admin."
)


def owner_only(func):
    @functools.wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        # Block specific user from block/unblock commands
        if message.from_user.id == 7005348098 and func.__name__ in ['lock_bot', 'unlock_bot']:
            return
        if message.from_user.id not in OWNERS:
            return
        return await func(client, message, *args, **kwargs)
    return wrapper



################################################################################################################################################################################################################################

#
# status.py implementation
#
async def send_status_update(client, message, identifier, content_info, status_type, extra_data=None, edit_message=None):
    """
    Sends or edits a status message for a download/upload task.
    If edit_message is provided, it edits that message. Otherwise, it sends a new one.
    """
    if extra_data is None:
        extra_data = {}

    try:
        user_id = int(identifier.split('_')[0])
        user = await client.get_users(user_id)
        user_mention = user.first_name or f"User (`{user_id}`)"
    except Exception:
        user_id = identifier.split('_')[0]
        user_mention = f"User (`{user_id}`)"

    title = content_info.get("title", "Unknown Title")
    episode_title = content_info.get("episode_title")
    platform = content_info.get("platform", "Unknown Platform")

    text = f"**👤 User:** {user_mention}\n"
    text += f"**✨ Platform:** {platform}\n"
    text += f"**🎬 Title:** {title}"
    if episode_title:
        text += f"\n**🎥 Episode:** {episode_title}"

    status_msg = None
    buttons = None

    if status_type == "download_start":
        resolution = extra_data.get('resolution', 'N/A')
        audio_tracks = extra_data.get('audio_tracks', 0)
        text += f"\n\n**📥 Status:** `Download Started`\n"
        text += f"**🖥️ Resolution:** `{resolution}`\n"
        text += f"**🔊 Audio Tracks:** `{audio_tracks}`"
    elif status_type == "upload_start":
        file_size = extra_data.get('file_size', 'N/A')
        text += f"\n\n**📤 Status:** `Upload Started`\n"
        text += f"**💾 File Size:** `{file_size}`"
    elif status_type == "download_failed":
        text += f"\n\n**❌ Status:** `Download Failed`"
        if extra_data.get('limit_type'):
             text += f"\n**🔄 Task Restored:** Your `{extra_data['limit_type']}` task limit has been restored. You now have **{extra_data['limit']}** tasks remaining."
    elif status_type == "stream_url_failed":
        text += f"\n\n**❌ Status:** `Failed`\n**Reason:** Could not retrieve stream URLs."
    elif status_type == "upload_unsuccessful":
        error = extra_data.get('error', 'Unknown error')
        text += f"\n\n**❌ Status:** `Upload Failed`\n"
        text += f"**Reason:** `{error}`"
        if extra_data.get('limit_type'):
             text += f"\n**🔄 Task Restored:** Your `{extra_data['limit_type']}` task limit has been restored. You now have **{extra_data['limit']}** tasks remaining."
    elif status_type in ["upload_complete_telegram", "upload_complete_drive"]:
        uploaded_msg_id = extra_data.get('uploaded_msg_id')
        text += f"\n\n**✅ Status:** `Upload Complete!`"
        if extra_data.get('limit_type'):
            text += f"\n**📊 Remaining Tasks:** You have **{extra_data['limit']}** `{extra_data['limit_type']}` tasks left."
        if uploaded_msg_id:
            link = f"https://t.me/c/{str(message.chat.id).replace('-100', '')}/{uploaded_msg_id}"
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("📂 View File", url=link)]])

    try:
        if edit_message:
            status_msg = await edit_message.edit_text(
                text=text,
                reply_markup=buttons,
                disable_web_page_preview=True
            )
        else:
            status_msg = await client.send_message(
                chat_id=message.chat.id,
                text=text,
                reply_markup=buttons,
                disable_web_page_preview=True
            )
    except MessageNotModified:
        status_msg = edit_message  # If not modified, return the original message object
    except Exception as e:
        logger.error(f"Failed to send/edit status update: {e}")

    return status_msg


async def get_thumbnail(identifier, video_file, download_dir):
    """
    Gets the thumbnail for a video.
    Priority:
    1. User's custom thumbnail from MongoDB.
    2. Thumbnail URL from content info.
    3. Generate thumbnail from video file.
    """
    user_id = int(identifier.split('_')[0])

    # 1. Check for user's custom thumbnail in MongoDB
    try:
        user_thumb_doc = await thumb_db.find_one({"_id": user_id})
        if user_thumb_doc and user_thumb_doc.get("thumb_id"):
            logger.info(f"Using custom thumbnail for user {user_id}.")
            return user_thumb_doc["thumb_id"]
    except Exception as e:
        logger.error(f"MongoDB error when fetching thumbnail for user {user_id}: {e}")

    # 2. Check for content-specific thumbnail from content_info
    try:
        with open('data/content_storage.json', 'r', encoding='utf-8') as f:
            content_storage = json.load(f)
        content_info = content_storage.get(identifier)
        if content_info and content_info.get("thumbnail"):
            thumb_url = content_info["thumbnail"]
            thumb_path = os.path.join(download_dir, "thumbnail.jpg")
            async with aiohttp.ClientSession() as session:
                async with session.get(thumb_url) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(thumb_path, mode='wb') as f:
                            await f.write(await resp.read())
                        return thumb_path
    except Exception as e:
        logger.warning(f"Could not download thumbnail from content info: {e}")

    # 3. Fallback to generating thumbnail from video file
    try:
        thumb_path = os.path.join(download_dir, "generated_thumb.jpg")
        
        process = await asyncio.create_subprocess_shell(
            f'ffmpeg -i "{video_file}" -ss 00:01:00.000 -vframes 1 -y "{thumb_path}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode == 0 and os.path.exists(thumb_path):
            return thumb_path
        else:
            logger.error(f"FFmpeg thumbnail generation failed: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}")
        return None

def construct_filename(content_info, identifier):
    """Constructs filename based on content type and audio streams."""
    # Get basic info
    title = content_info.get("title", "Unknown")
    title = title.replace(" ", ".").replace("'", ".").replace("'", ".") if title else "Unknown"
    content_type = content_info.get("content_type", "")
    year = content_info.get("year", "")
    platform = content_info.get("platform", "")

    # Get selected resolution and audio from callback storage
    try:
        with open('data/callback_storage.json', 'r', encoding='utf-8') as f:
            callback_data = json.load(f).get(identifier, {})

            # Get resolution
            selected_res = callback_data.get("selected_resolution", {})
            max_resolution = "1080p"  # Default

            if selected_res:
                width, height = selected_res["resolution"].split("x")
            else:
                # Fallback to highest available resolution
                video_streams = content_info.get("streams_info", {}).get("video", [])
                if video_streams:
                    width, height = video_streams[0]["resolution"].split("x")
                else:
                    width, height = "1920", "1080"  # Default fallback

            width = ''.join(c for c in width if c.isdigit())
            height = ''.join(c for c in height if c.isdigit())
            max_resolution = "1080p" if width == "1920" else f"{height}p"

            # Get selected audios
            selected_audio_ids = callback_data.get("selected_audios", [])

    except Exception as e:
        logger.error(f"Error reading callback storage: {e}")
        # Fallback to highest available resolution
        video_streams = content_info.get("streams_info", {}).get("video", [])
        max_resolution = "1080p"  # Default
        if video_streams:
            width, height = video_streams[0]["resolution"].split("x")
            width = ''.join(c for c in width if c.isdigit())
            height = ''.join(c for c in height if c.isdigit())
            max_resolution = "1080p" if width == "1920" else f"{height}p"
        selected_audio_ids = []

    # Get audio info based on selected audios
    audio_streams = content_info.get("streams_info", {}).get("audio", [])
    selected_audio_streams = [stream for stream in audio_streams if stream["stream_id"] in selected_audio_ids]

    # Determine audio type string based on selected audios
    is_tataplay = platform == "TataPlay"

    if is_tataplay:
        # For TataPlay, use language codes in order of selection
        audio_languages = []
        for audio_id in selected_audio_ids:
            for stream in selected_audio_streams:
                if stream["stream_id"] == audio_id:
                    audio_languages.append(stream["language"].upper()[:3])
                    break
        audio_type = "-".join(audio_languages) if audio_languages else ""
        audio_codec = ""
        video_codec = ""
    else:
        # For other platforms, use the original logic
        unique_languages = len(set(audio["language"] for audio in selected_audio_streams))

        if unique_languages == 0:
            audio_type = ""  # Empty for no audio
        elif unique_languages == 1:
            lang = selected_audio_streams[0]["language"]
            audio_type = "" if lang.upper() in ["UND", "UNKNOWN", "None"] else lang
        elif unique_languages == 2:
            audio_type = ""
        else:
            audio_type = ""

        # Set audio codec to DDP.5.1 for all platforms except TataPlay
        audio_codec = ""
        # Set video codec based on platform
        video_codec = "" if platform in ["JioHotstar", "Amazon Prime"] else ""
        # Add HDR tag for 2160p jStar content
        if max_resolution == "2160p" and platform in ["JioHotstar", "Amazon Prime"]:
            video_codec = ""

    # Use platform_suffix from content_info if available, otherwise use from mapping
    platform_suffix = content_info.get("platform_suffix") or PLATFORM_SUFFIXES.get(platform, "UNK")

    def clean_name(text):
        # Helper function to handle both existing and new hyphen removal
        cleaned = text
        if "–" in cleaned:
            cleaned = cleaned.split("–", 1)[-1].strip()
        return cleaned.replace("–.", "").replace("-", "")

    # For TataPlay, keep the original title format with brackets
    clean_title = title if is_tataplay else clean_name(title)

    # Construct filename based on content type
    if content_type == "EPISODE":
        # Get episode number directly from content_info
        episode_number = content_info.get("episode_number", "S01E01")
        episode_title = content_info.get("episode_title", "")

        if episode_title:
            cleaned_episode_title = clean_name(episode_title)
            filename = f"{clean_title}.{episode_number}.{cleaned_episode_title}"
        else:
            filename = f"{clean_title}.{episode_number}"
    else:
        # For movies: title.year
        filename = f"{clean_title}.{year}" if year and year != "N/A" else clean_title

    # Add quality and other specs
    filename = f"{METASUFFIX}.{filename}.{max_resolution}.{platform_suffix}.WEB-DL.{audio_type}.{audio_codec}.{video_codec}"

    # Clean filename - replace spaces, quotes, invalid chars with dots, but keep brackets for TataPlay
    invalid_chars = r'[ \'"<>:"/\\|?*$]|None' if is_tataplay else r'[ \'"<>:"/\\|?*$\[\]]|None'
    filename = re.sub(invalid_chars, '.', filename)

    # Remove multiple dots and leading/trailing dots
    filename_dot_separated = re.sub(r'\.+', '.', filename).strip('.')
    return filename_dot_separated.replace('.', ' ')


import logging
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import os
import time
import json

# Configure logger
logger = logging.getLogger(__name__)

# Load configuration from helpers.config
try:
    from helpers.config import pickFormats
except ImportError:
    # Fallback if import fails
    pickFormats = {
        "audio": {
            "eng": "English",
            "hin": "Hindi",
            "tam": "Tamil",
            "tel": "Telugu",
            "ben": "Bengali",
            "kan": "Kannada",
            "mal": "Malayalam",
            "mar": "Marathi"
        }
    }

def load_callback_storage():
    """Load callback storage from JSON file."""
    try:
        os.makedirs('data', exist_ok=True)
        storage_path = 'data/callback_storage.json'

        try:
            with open(storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                current_time = time.time()
                # Filter out entries older than 60 minutes
                return {k: v for k, v in data.items()
                       if (v.get("selected_audios") or v.get("selected_resolution"))
                       and current_time - v.get('timestamp',0) < 3600}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    except Exception as e:
        logger.error(f"Error loading callback storage: {e}")
        return {}

def save_callback_storage(data):
    """Save callback storage to JSON file."""
    try:
        os.makedirs('data', exist_ok=True)
        storage_path = 'data/callback_storage.json'

        # Add timestamp to entries
        import time
        current_time = time.time()
        for v in data.values():
            v['timestamp'] = current_time

        cleaned_data = {k: v for k, v in data.items()
                       if (v.get("selected_audios") or v.get("selected_resolution"))
                       and current_time - v.get('timestamp',0) < 3600}

        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving callback storage: {e}")
        return False

def get_selected_audios(identifier, callback_storage=None):
    """Get selected audio streams for a given identifier."""
    return (callback_storage or load_callback_storage()).get(identifier, {}).get("selected_audios", [])

def create_resolution_buttons(identifier, streams_info, content_info=None):
    buttons = []
    row = []

    # Check if this is TMDB content
    is_tmdb = False

    # Use content_info directly to determine if this is TMDB content
    if content_info and content_info.get("platform") == "TMDB":
        is_tmdb = True
        logger.info(f"TMDB content detected for {identifier}")

    # Get videos to display
    if is_tmdb:
        # For TMDB, use videos as they are, no sorting needed
        videos_to_display = streams_info["video"]
        logger.info(f"Using TMDB display for {len(videos_to_display)} videos with display names")
    else:
        # Remove duplicates keeping highest bitrate for each stream_id
        seen_stream_ids = {}
        for video in streams_info["video"]:
            stream_id = video["stream_id"]
            if stream_id not in seen_stream_ids or video["bitrate"] > seen_stream_ids[stream_id]["bitrate"]:
                seen_stream_ids[stream_id] = video

        # Sort video streams by resolution height and bitrate
        videos_to_display = sorted(
            seen_stream_ids.values(),
            key=lambda x: (int(''.join(c for c in x["resolution"].split("x")[1] if c.isdigit())), x["bitrate"]),
            reverse=True
        )

    # Create buttons for each video
    for video in videos_to_display:
        # Shorten stream_id by taking the last segment after underscore
        stream_id_parts = video["stream_id"].split("_")
        short_id = stream_id_parts[-1] if len(stream_id_parts) > 1 else video["stream_id"]

        # Create button text based on platform
        if is_tmdb:
            # For TMDB, just use the display_name directly without modification
            button_text = video.get("display_name", "Unknown")
            logger.info(f"Creating TMDB button with text: {button_text}")
        else:
            # For other platforms, use resolution and bitrate
            # Extract width and height from resolution
            width, height = video["resolution"].split("x")
            width = ''.join(c for c in width if c.isdigit())
            height = ''.join(c for c in height if c.isdigit())

            # If width is 1920, force display height as 1080
            display_height = "1080" if width == "1920" else height

            button_text = f"{display_height}p ({video['bitrate']}K)"

        # Create callback data
        callback_data = f"res_{identifier}_{short_id}"

        # Ensure callback data doesn't exceed 64 bytes
        if len(callback_data.encode()) > 64:
            # Shorten identifier by using first 8 characters of user ID
            short_identifier = f"{identifier.split('_')[0][:8]}_{identifier.split('_')[1]}"
            callback_data = f"res_{short_identifier}_{short_id}"

        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("❌ Close", callback_data=f"close_{identifier}")])

    return InlineKeyboardMarkup(buttons)

def create_audio_buttons(identifier, streams_info, selected_resolution=None):
    buttons = []
    row = []
    callback_storage = load_callback_storage()
    selected_audios = get_selected_audios(identifier, callback_storage)

    # Group and sort audio streams by language
    audio_streams_by_lang = {}
    for audio in streams_info["audio"]:
        lang_code = audio["language"].lower()[:3]
        if lang_code not in audio_streams_by_lang:
            audio_streams_by_lang[lang_code] = []
        audio_streams_by_lang[lang_code].append(audio)

    for streams in audio_streams_by_lang.values():
        streams.sort(key=lambda x: x["bitrate"], reverse=True)

    # Prioritize and filter streams
    prioritized = []
    other = []
    for lang_code, streams in audio_streams_by_lang.items():
        if lang_code in pickFormats["audio"]:
            prioritized.extend(streams)
        else:
            other.extend(streams[:2])

    audio_streams = prioritized + other[:5]

    # Setup callback storage
    if identifier not in callback_storage:
        callback_storage[identifier] = {"stream_id_map": {}}
    elif "stream_id_map" not in callback_storage[identifier]:
        callback_storage[identifier]["stream_id_map"] = {}

    # Group by language+bitrate and filter duplicates
    lang_bitrate_groups = {}
    for audio in audio_streams:
        key = f"{audio['language'].lower()[:3]}_{audio['bitrate']}"
        if key not in lang_bitrate_groups:
            lang_bitrate_groups[key] = []
        lang_bitrate_groups[key].append(audio)

    filtered_streams = []
    for streams in lang_bitrate_groups.values():
        # Include all duplicates instead of limiting to 3
        filtered_streams.extend(streams)

    filtered_streams.sort(key=lambda x: (
        x["language"].lower()[:3] not in pickFormats["audio"],
        -x["bitrate"]
    ))

    # Create buttons
    for idx, audio in enumerate(filtered_streams, 1):
        lang_code = audio["language"].lower()[:3]
        lang_name = pickFormats["audio"].get(lang_code, audio["language"])

        # Add stream_id suffix for duplicates
        suffix = ""
        if any(a != audio and
               a["language"].lower()[:3] == lang_code and
               a["bitrate"] == audio["bitrate"]
               for a in filtered_streams):
            suffix = f" ({audio['stream_id']})"

        button_text = f"{idx}. {lang_name} ({audio['bitrate']}K){suffix}"
        if audio["stream_id"] in selected_audios:
            button_text = "✅ " + button_text

        # Store mapping and create callback
        stream_index = str(idx)
        callback_storage[identifier]["stream_id_map"][stream_index] = audio["stream_id"]

        callback_data = f"aud_{identifier}_{stream_index}"
        if len(callback_data.encode()) > 64:
            short_id = f"{identifier.split('_')[0][:8]}_{identifier.split('_')[1]}"
            callback_data = f"aud_{short_id}_{stream_index}"

        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    save_callback_storage(callback_storage)

    # Add Select All and Clear All buttons


    # Add navigation buttons
    buttons.extend([
        [
            InlineKeyboardButton("⬅️ Back", callback_data=f"back_{identifier}"),
            InlineKeyboardButton("Proceed ➡️", callback_data=f"proc_{identifier}")
        ],
        [InlineKeyboardButton("❌ Close", callback_data=f"close_{identifier}")]
    ])

    return InlineKeyboardMarkup(buttons)

async def handle_proceed_download(client, message, content_info, selected_resolution, selected_audios, identifier, progress_msg, retry_count=0):
    download_dir = get_isolated_download_path(identifier)
    is_trial = False
    downloader = None
    user_id_str = identifier.split('_')[0]

    try:
        user_id = int(user_id_str)
        chat_id = message.chat.id
        is_trial = (user_id not in get_full_access_users() and chat_id not in get_full_access_users()) and \
                   (user_id in TRIAL_ACCESS or chat_id in TRIAL_ACCESS)

        async with download_semaphore:
            platform = content_info.get("platform", "").upper()
            filename = construct_filename(content_info, identifier)
            file_path = os.path.join(download_dir, filename)
            
            magnet_url = ""
            file_idx = None
            display_name = selected_resolution.get('display_name', selected_resolution.get('resolution', 'Unknown quality'))

            if platform == "TMDB" and "magnet_streams" in content_info:
                stream_id = selected_resolution.get("stream_id", "")
                for name, stream_data in content_info["magnet_streams"].items():
                    if (stream_data.get("stream_id", "") == stream_id) or (not stream_id and name == display_name):
                        magnet_url = stream_data.get("url", "")
                        file_idx = stream_data.get("fileIdx", None)
                        logger.info(f"Found matching magnet link for {display_name}")
                        break
                if not magnet_url:
                    raise Exception(f"Could not find magnet link for stream_id {stream_id} or display_name {display_name}")
                downloader = QBitDownloader(magnet_url=magnet_url, selected_resolution=selected_resolution, selected_audios=selected_audios, content_info=content_info, download_dir=download_dir, filename=filename, identifier=identifier, file_idx=file_idx)
            else:
                stream_url = content_info["streams"].get("dash") or content_info["streams"].get("hls")
                if not stream_url:
                    raise Exception("Could not retrieve stream URLs.")
                platform_lower = platform.lower()
                formats_from_parser = content_info.get("formats_from_parser", False)
                if (platform_lower in ["amazon prime", "tubi", "pluto tv", "hbo max", "ullu", "etv win", "mxplayer"] and not formats_from_parser) or \
                   (platform_lower == "jiohotstar" and ("hls" in stream_url or "m3u8" in stream_url or (stream_url.startswith("https://hses") and "vod-cf.cdn.hotstar.com" in stream_url) or stream_url.startswith("https://ab"))) or \
                   (platform_lower == "airtel xstream" and ("hls" in stream_url or "m3u8" in stream_url)):
                    downloader = YTDLPDownloader(stream_url=content_info["streams"]["dash"], selected_resolution=selected_resolution, selected_audios=selected_audios, content_info=content_info, download_dir=download_dir, filename=filename, identifier=identifier)
                else:
                    downloader = Nm3u8DLREDownloader(stream_url=content_info["streams"]["dash"], selected_resolution=selected_resolution, selected_audios=selected_audios, content_info=content_info, download_dir=download_dir, filename=filename, identifier=identifier)

            return_code = await downloader.execute()

            if return_code != 0:
                raise Exception("Download process failed with a non-zero exit code.")
            
            if isinstance(downloader, YTDLPDownloader) or isinstance(downloader, QBitDownloader):
                final_file_path = downloader.final_merged_path
            else:
                extension = "mp4" if user_id_str in MP4_USER_IDS else "mkv"
                final_file_path = f"{file_path}.{extension}"

            if not os.path.exists(final_file_path):
                raise Exception(f"Final file not found at {final_file_path}")

            process = await asyncio.create_subprocess_shell(f'ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "{final_file_path}"', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            audio_codec = (await process.communicate())[0].decode().strip()
            process = await asyncio.create_subprocess_shell(f'ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,color_transfer -of default=noprint_wrappers=1:nokey=1 "{final_file_path}"', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            output = (await process.communicate())[0].decode().strip().split('\n')
            video_codec = output[0]
            is_hdr = len(output) > 1 and output[1] in ['smpte2084', 'arib-std-b67']

            if audio_codec == "aac": filename = filename.replace("DDP 5 1", "AAC 2 0")
            if video_codec == "h264": filename = filename.replace("H265", "H264")
            elif video_codec == "hevc": filename = filename.replace("H264", "H265")
            if not is_hdr and "HDR" in filename: filename = filename.replace("HDR", "SDR")

            new_final_path = os.path.join(download_dir, f"{filename}.mkv")
            os.rename(final_file_path, new_final_path)
            final_file_path = new_final_path

            temp_output = os.path.join(download_dir, "temp_output.mkv")
            ffmpeg_cmd = [f'ffmpeg -y -v verbose -i "{final_file_path}"', ' -map 0:v -map 0:a -map 0:s?', f' -c:v copy -c:a copy -c:s copy -metadata:s:a title="[{METASUFFIX}]"', f' "{temp_output}"']
            process = await asyncio.create_subprocess_shell(''.join(ffmpeg_cmd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await process.communicate()

            if process.returncode == 0:
                os.remove(final_file_path)
                os.rename(temp_output, final_file_path)
            elif os.path.exists(temp_output):
                os.remove(temp_output)
            
            subtitle_dir = None
            subtitle_files = []
            if (platform.lower() == "hbo max" and content_info["streams"].get("dash")) or ('subtitles' in content_info and content_info['subtitles']):
                subtitle_dir = os.path.join(download_dir, 'subs')
                os.makedirs(subtitle_dir, exist_ok=True)
                if platform.lower() == "hbo max" and content_info["streams"].get("dash"):
                    stream_url = content_info["streams"]["dash"]
                    nm3u8dl_cmd = f'N_m3u8DL-RE "{stream_url}" --save-dir "{subtitle_dir}" --drop-video all --drop-audio all --select-subtitle all --sub-format SRT'
                    process = await asyncio.create_subprocess_shell(nm3u8dl_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    await process.communicate()
                    if process.returncode == 0:
                        for file in os.listdir(subtitle_dir):
                            if file.endswith(".srt"):
                                match = re.search(r'\.([a-z]{2}(?:-[A-Z]{2})?)(?:\.copy)*\.srt$', file)
                                lang_code = match.group(1).split('-')[0].lower() if match else 'und'
                                subtitle_files.append((os.path.join(subtitle_dir, file), lang_code))
                elif 'subtitles' in content_info and content_info['subtitles']:
                    async def process_subtitle(subtitle, subtitle_dir):
                        try:
                            sub_url = subtitle['url']
                            language_code = subtitle['languageCode'].lower().split('-')[0]
                            if not re.match(r'^[a-z]{2,3}$', language_code): return None
                            is_vtt = subtitle.get('format', '').lower() == 'vtt'
                            final_subtitle_path = os.path.join(subtitle_dir, f"{language_code}.srt")
                            temp_path = os.path.join(subtitle_dir, f"{language_code}.{'vtt' if is_vtt else 'ttml2'}")
                            if is_vtt:
                                headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"}
                                async with aiohttp.ClientSession() as session:
                                    async with session.get(sub_url, headers=headers, proxy=PROXY_URL if USE_PROXY else None) as response:
                                        if response.status == 200:
                                            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f: await f.write(await response.text())
                            else:
                                process = await asyncio.create_subprocess_shell(f'curl -s -x {PROXY_URL} "{sub_url}" -o "{temp_path}"', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                                await process.communicate()
                                if process.returncode != 0: return None
                            if await (vtt_to_srt if is_vtt else ttml_to_srt)(temp_path, final_subtitle_path):
                                try: os.remove(temp_path)
                                except OSError: pass
                                return (final_subtitle_path, language_code)
                            return None
                        except Exception: return None
                    results = await asyncio.gather(*[process_subtitle(sub, subtitle_dir) for sub in content_info['subtitles']])
                    subtitle_files = [r for r in results if r]
                if subtitle_files:
                    indian_langs = ['hi', 'ta', 'te', 'kn', 'ml', 'bn', 'gu', 'mr', 'pa', 'tam', 'tel', 'kan', 'mal', 'ben', 'mar', 'hin']
                    subtitle_files.sort(key=lambda x: (0 if x[1] == 'en' else 1 if x[1] in indian_langs else 2, x[1]))
                    temp_output = os.path.join(download_dir, "temp_output.mkv")
                    ffmpeg_cmd = [f'ffmpeg -y -v quiet -i "{final_file_path}"', *[f' -i "{sub_path}"' for sub_path, _ in subtitle_files], ' -map 0:v -map 0:a -map 0:s?', *[f' -map {i}:0 -metadata:s:s:{i-1 if "0:s" not in ffmpeg_cmd[2] else i} language={get_iso_639_2(lang_code)}' for i, (_, lang_code) in enumerate(subtitle_files, 1)], f' -c:v copy -c:a copy -c:s srt -metadata:s:a title="[{METASUFFIX}]" -metadata:s:s title="[{METASUFFIX}]"', f' "{temp_output}"']
                    try:
                        process = await asyncio.create_subprocess_shell(''.join(ffmpeg_cmd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        await process.communicate()
                        if process.returncode == 0:
                            verify_process = await asyncio.create_subprocess_shell(f'ffprobe -v error -select_streams s -show_entries stream=index:stream_tags=language -of csv=p=0 "{temp_output}"', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                            verify_stdout, _ = await verify_process.communicate()
                            muxed_subs = verify_stdout.decode().strip().split('\n') if verify_stdout.decode().strip() else []
                            if len(muxed_subs) >= len(subtitle_files):
                                os.remove(final_file_path)
                                os.rename(temp_output, final_file_path)
                            else: os.remove(temp_output)
                        elif os.path.exists(temp_output): os.remove(temp_output)
                    except Exception as e:
                        if os.path.exists(temp_output):
                            try: os.remove(temp_output)
                            except OSError: pass
                if subtitle_dir and os.path.exists(subtitle_dir):
                    try: shutil.rmtree(subtitle_dir, ignore_errors=True)
                    except Exception: pass
            
            progress_data = download_progress.get_task_progress(identifier)
            progress_data['status'] = 'Upload'
            download_progress.update_progress(identifier, progress_data)

            upload_success = await upload_video(client, message, final_file_path, filename, download_dir, identifier, progress_msg)

            if not upload_success:
                raise Exception("Upload failed.")

            return True

    except asyncio.CancelledError:
        logger.info(f"Task {identifier} was cancelled by user.")
        await progress_msg.edit_text(f"❌ **Task `{identifier}` has been cancelled.**")
        if is_trial:
            try:
                with open('data/user_plans.json', 'r+') as f:
                    user_plans = json.load(f)
                    res = selected_resolution.get('resolution', '')
                    height = int(res.split('x')[1]) if 'x' in res else 0
                    limit_type = "720p" if height <= 720 else "1080p"
                    user_plans[user_id_str][f"{limit_type}_limit"] += 1
                    f.seek(0); json.dump(user_plans, f, indent=4); f.truncate()
            except Exception as e:
                logger.error(f"Failed to restore task limit on cancellation: {e}")
        cleanup_download_dir(download_dir)
        download_progress.clear_task(identifier)
        return False

    except Exception as e:
        logger.error(f"Error in handle_proceed_download for {identifier}: {e}", exc_info=True)
        await progress_msg.edit_text(f"❌ **An error occurred:**\n`{str(e)}`")
        if is_trial:
            try:
                with open('data/user_plans.json', 'r+') as f:
                    user_plans = json.load(f)
                    res = selected_resolution.get('resolution', '')
                    height = int(res.split('x')[1]) if 'x' in res else 0
                    limit_type = "720p" if height <= 720 else "1080p"
                    user_plans[user_id_str][f"{limit_type}_limit"] += 1
                    f.seek(0); json.dump(user_plans, f, indent=4); f.truncate()
            except Exception as plan_e:
                logger.error(f"Failed to restore task limit on failure: {plan_e}")
        cleanup_download_dir(download_dir)
        download_progress.clear_task(identifier)
        return False

class DownloadProgress:
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()

    def update_progress(self, identifier, progress_data):
        """Update progress for a task using our existing progress_data structure"""
        with self.lock:
            if identifier not in self.tasks:
                self.tasks[identifier] = {}
            
            # This allows partial updates
            for key, value in progress_data.items():
                if key == 'audio' and 'audio' in self.tasks[identifier]:
                    self.tasks[identifier]['audio'].update(value)
                elif key == 'upload' and 'upload' in self.tasks[identifier]:
                    self.tasks[identifier]['upload'].update(value)
                else:
                    self.tasks[identifier][key] = value

    def get_task_progress(self, identifier):
        """Get progress for a specific task"""
        with self.lock:
            return self.tasks.get(identifier, {})

    def clear_task(self, identifier):
        """Clear progress data for a task"""
        with self.lock:
            if identifier in self.tasks:
                # Cancel any associated tasks before clearing
                main_task = self.tasks[identifier].get('main_task')
                if main_task and not main_task.done():
                    main_task.cancel()
                updater_task = self.tasks[identifier].get('updater_task')
                if updater_task and not updater_task.done():
                    updater_task.cancel()
            self.tasks.pop(identifier, None)

class ProgressDisplay:
    def __init__(self):
        self.progress_bar_length = 10
        self.processing_frames = ["⠏", "⠹", "⠼", "⠧", "⠋", "⠙", "⠸", "⠴", "⠦", "⠇"]
        self.current_frame = 0
        self.user_pages = {}  # Dictionary to store current page for each user
        self.active_task_messages = {}  # Dictionary to store active task messages per chat
        self.lock = asyncio.Lock()  # Async lock for thread safety

    def create_progress_bar(self, percentage):
        filled = int(self.progress_bar_length * percentage / 100)
        return '▰' * filled + '▱' * (self.progress_bar_length - filled)

    async def get_next_processing_frame(self):
        async with self.lock:
            frame = self.processing_frames[self.current_frame]
            self.current_frame = (self.current_frame + 1) % len(self.processing_frames)
            return frame

    async def calculate_average_progress(self, progress_data):
        """Calculate average progress across all streams"""
        video_percentage = 0
        if progress_data.get('video'):
            video_percentage = progress_data['video'].get('percentage', 0)
            if isinstance(video_percentage, str):
                try: video_percentage = float(video_percentage)
                except (ValueError, TypeError): video_percentage = 0
        
        audio_percentages = []
        if progress_data.get('audio'):
            for audio in progress_data['audio'].values():
                percentage = audio.get('percentage', 0)
                if isinstance(percentage, str):
                    try: percentage = float(percentage)
                    except (ValueError, TypeError): percentage = 0
                audio_percentages.append(percentage)

        total = video_percentage + sum(audio_percentages)
        count = 1 + len(audio_percentages)
        return round(total / count if count else 0, 1)

    async def get_real_status(self, progress_data):
        """Determine the real status based on progress"""
        status = progress_data.get('status', 'Download')
        if status == 'Upload': return 'Upload'
        avg_progress = await self.calculate_average_progress(progress_data)
        if avg_progress >= 100: return 'Post Processing'
        return 'Download'

    async def calculate_total_speed(self, progress_data):
        """Calculate total speed from all streams"""
        def convert_speed_to_kbps(speed_str):
            try:
                value = float(re.findall(r"[\d\.]+", speed_str)[0])
                if 'MBps' in speed_str: return value * 1024
                if 'KBps' in speed_str: return value
                return 0
            except: return 0

        total_speed_kbps = 0
        if progress_data.get('video'):
            total_speed_kbps += convert_speed_to_kbps(progress_data['video'].get('speed', '0 KBps'))
        if progress_data.get('audio'):
            for audio in progress_data['audio'].values():
                total_speed_kbps += convert_speed_to_kbps(audio.get('speed', '0 KBps'))

        if total_speed_kbps >= 1024: return f"{total_speed_kbps/1024:.2f} MB/s"
        return f"{total_speed_kbps:.2f} KB/s"

    async def format_audio_progress_compact(self, progress_data):
        """Format audio progress into a compact single line."""
        if not progress_data.get('audio'):
            return "N/A"

        normalized_data = {}
        for lang_code, audio in progress_data['audio'].items():
            norm_lang_code = lang_code.lower()
            percentage = float(audio.get('percentage', 0))

            if norm_lang_code not in normalized_data or percentage > normalized_data[norm_lang_code]['percentage']:
                normalized_data[norm_lang_code] = {
                    'percentage': percentage,
                    'display_name': pickFormats['audio'].get(norm_lang_code, lang_code.title())
                }

        sorted_langs = sorted(normalized_data.items(), key=lambda x: (-x[1]['percentage'], x[0]))

        parts = []
        for _, data in sorted_langs:
            lang_short = data['display_name'][:3]
            progress_text = "✅" if data['percentage'] >= 100 else f"{data['percentage']:.0f}%"
            parts.append(f"{lang_short}: {progress_text}")
            if len(parts) >= 3:
                break
        
        return " | ".join(parts) if parts else "N/A"


    async def parse_video_progress(self, line, identifier):
        """Parse video progress from a line"""
        try:
            resolution = re.search(r'Vid (\d+x\d+)', line)
            resolution = resolution.group(1) if resolution else "N/A"
            bitrate = re.search(r'(\d+ Kbps)', line)
            bitrate = bitrate.group(1) if bitrate else "N/A"
            progress_match = re.search(r'(\d+)/(\d+)\s+([\d\.]+)%', line)
            size_match = re.search(r'([\d\.]+(?:MB|GB))/([\d\.]+(?:MB|GB))', line)
            speed_match = re.search(r'([\d\.]+(?:MBps|KBps))', line)
            eta_match = re.search(r'(\d{2}:\d{2}:\d{2}|\d{2}:\d{2})', line)

            return {
                'resolution': resolution,
                'bitrate': bitrate,
                'percentage': float(progress_match.group(3)) if progress_match else 0,
                'downloaded_size': size_match.group(1) if size_match else "0MB",
                'total_size': size_match.group(2) if size_match else "0MB",
                'speed': speed_match.group(1) if speed_match else "0 KBps",
                'eta': eta_match.group(1) if eta_match else "00:00"
            }
        except Exception as e:
            logger.error(f"Error parsing video progress for {identifier}: {e}")
            return None
            
    async def parse_audio_progress(self, line, identifier):
        """Parse audio progress from a line"""
        try:
            lang_match = re.search(r'Aud \d+ Kbps \| ([a-zA-Z0-9]+)', line)
            lang = lang_match.group(1) if lang_match else "Unknown"
            
            progress_match = re.search(r'(\d+)/(\d+)\s+([\d\.]+)%', line)
            
            return lang.title(), {
                'percentage': float(progress_match.group(3)) if progress_match else 0,
            }
        except Exception as e:
            logger.error(f"Error parsing audio progress for {identifier}: {e}")
            return None, None

    async def update_progress_from_line(self, line, progress_data, identifier):
        """Update progress data from a line based on identifier"""
        if line.startswith('Vid'):
            video_progress = await self.parse_video_progress(line, identifier)
            if video_progress:
                if 'video' not in progress_data: progress_data['video'] = {}
                progress_data['video'].update(video_progress)

        elif line.startswith('Aud'):
            lang, audio_progress = await self.parse_audio_progress(line, identifier)
            if lang and audio_progress:
                if 'audio' not in progress_data: progress_data['audio'] = {}
                progress_data['audio'][lang] = audio_progress

        return progress_data

    async def format_task_progress(self, identifier, progress_data):
        if not progress_data: return ""

        # --- Get base info ---
        title = progress_data.get('filename', 'Unknown Title')
        title = title.replace(".", " ").rsplit('-', 1)[0] # Clean up title
        platform = progress_data.get('platform', 'N/A')
        status = await self.get_real_status(progress_data)
        
        try:
            user_id = int(identifier.split('_')[0])
            user = await app.get_users(user_id)
            user_mention = user.mention
        except Exception:
            user_mention = f"User (`{identifier.split('_')[0]}`)"
        
        # --- Build the message ---
        message = [f"🎬 **{title}**", f"✨ **Platform:** `{platform}`"]

        # --- Status-specific sections ---
        if status == 'Upload':
            upload_data = progress_data.get('upload', {})
            upload_progress = upload_data.get('percentage', 0)
            progress_bar = self.create_progress_bar(upload_progress)
            
            message.extend([
                "\n📤 **UPLOADING...**",
                f"`{progress_bar}` **{upload_progress:.1f}%**",
                f" ├─ 🚀 **Speed:** `{upload_data.get('speed', 'N/A')}`",
                f" ├─ 💾 **Size:** `{upload_data.get('current_size', 'N/A')} / {upload_data.get('total_size', 'N/A')}`",
                f" ╰─ ⏳ **ETA:** `{upload_data.get('eta', 'N/A')}`",
            ])

        elif status == 'Post Processing':
            spinner = await self.get_next_processing_frame()
            message.extend([
                f"\n🔄 **PROCESSING...** {spinner}",
                "   `Merging video, audio, and subtitles...`"
            ])
            
        else: # Downloading
            total_progress = await self.calculate_average_progress(progress_data)
            progress_bar = self.create_progress_bar(total_progress)
            total_speed = await self.calculate_total_speed(progress_data)
            
            video_info = progress_data.get('video', {})
            video_percentage = float(video_info.get('percentage', 0))
            eta = video_info.get('eta', 'N/A')
            
            resolution = "N/A"
            if video_info.get('resolution'):
                width, height = video_info['resolution'].split('x')
                resolution = f"{'1080' if width == '1920' else height}p"

            audio_line = await self.format_audio_progress_compact(progress_data)

            message.extend([
                "\n📥 **DOWNLOADING...**",
                f"`{progress_bar}` **{total_progress:.1f}%**",
                f" ├─ 🚀 **Speed:** `{total_speed}`",
                f" ├─ ⏳ **ETA:** `{eta}`",
                f" ├─ 🖥️ **Video:** `{resolution} ({video_percentage:.1f}%)`",
                f" ╰─ 🔊 **Audio:** `{audio_line}`",
            ])
        
        message.append(f"\n👤 **User:** {user_mention}")
        return "\n".join(message)


    async def format_all_progress(self, download_progress, page=1):
        active_tasks = len(download_progress.tasks)
        if not active_tasks:
            return None, None

        header = [
            f"**⚜️ ACTIVE DOWNLOADS: {active_tasks} ⚜️**\n"
        ]

        tasks_per_page = 5
        total_pages = (active_tasks + tasks_per_page - 1) // tasks_per_page
        start_idx = (page - 1) * tasks_per_page
        end_idx = min(start_idx + tasks_per_page, active_tasks)

        task_sections = []
        for identifier, progress_data in list(download_progress.tasks.items())[start_idx:end_idx]:
            task_progress = await self.format_task_progress(identifier, progress_data)
            task_sections.extend([task_progress, "⎯" * 20])

        footer = [f"**Page {page}/{total_pages}**"]

        buttons = []
        if active_tasks > tasks_per_page:
            row = []
            if page > 1: row.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
            row.append(InlineKeyboardButton("🔄", callback_data=f"refresh_{page}"))
            if page < total_pages: row.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
            buttons.append(row)

        return "\n".join(header + task_sections + footer), buttons if buttons else None

download_progress = DownloadProgress()
progress_display = ProgressDisplay()

# Export to helpers.download module to avoid circular imports
from helpers import download as download_module
download_module.download_progress = download_progress
download_module.progress_display = progress_display

# Helper function for resource cleanup
async def cleanup_resources(thumb, download_dir, display_filename):
    # Close any open file handles before cleanup
    if thumb and isinstance(thumb, str) and await asyncio.to_thread(os.path.exists, thumb):
        try:
            # Forcibly close file handle if necessary, though just removing should be enough
            # This part can be tricky and platform-dependent, often removal is sufficient
            pass
        except:
            pass
    await asyncio.sleep(1)
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        try:
            await asyncio.to_thread(shutil.rmtree, download_dir, ignore_errors=True)
            break
        except Exception as e:
            logger.error(f"Cleanup attempt {retry_count + 1} failed: {e}")
            retry_count += 1
            await asyncio.sleep(2)
    try:
        if await asyncio.to_thread(os.path.exists, display_filename):
            await asyncio.to_thread(os.remove, display_filename)
    except Exception as e:
        logger.error(f"Failed to remove copied file: {e}")

# Refactoring upload_video into a class
class VideoUploader:
    """Class for handling video uploads to Telegram or Google Drive."""

    def __init__(self, client, message, file_path, filename, download_dir, identifier, progress_msg=None):
        """Initialize the VideoUploader with necessary parameters."""
        self.client = client
        self.message = message
        self.file_path = file_path
        self.filename = filename
        self.download_dir = download_dir
        self.identifier = identifier
        self.progress_msg = progress_msg
        self.premium_client = None
        self.thumb = None
        self.progress_data = None
        self.content_info = {}
        self.uploaded_msg = None
        self.use_rclone = False
        self.is_trial = False
        self.is_partial = False
        self.channel_id = -1002784327959  # Channel ID for uploads

    async def upload(self):
        """Main method to handle the video upload process."""
        async with upload_semaphore:  # Use semaphore to control concurrent uploads
            try:
                await self._initialize_upload()
                await self._determine_upload_method()

                if self.use_rclone:
                    await self._upload_via_rclone()
                else:
                    await self._upload_via_telegram()

                if self.uploaded_msg:
                    await self._send_completion_message()

                # Clean up and return success
                await self._cleanup()
                return True

            except Exception as e:
                logger.error(f"Upload failed: {e}", exc_info=True)
                await self._handle_upload_failure(e)
                return False

            finally:
                await self._finalize()

    async def _initialize_upload(self):
        """Initialize upload by setting up necessary data and configurations."""
        user_id = str(self.identifier.split('_')[0])
        chat_id = self.message.chat.id
        self.user_id = user_id
        self.chat_id = chat_id
        self.is_trial = (int(user_id) not in get_full_access_users() and chat_id not in get_full_access_users()) and \
                        (int(user_id) in TRIAL_ACCESS or chat_id in TRIAL_ACCESS)

        try:
            user = await self.client.get_users(int(user_id))
            self.user_mention = user.mention
        except Exception as e:
            self.user_mention = f"[{user_id}](tg://user?id={user_id})"

        extension = "mp4" if user_id in MP4_USER_IDS else "mkv"
        self.display_filename = f"{self.filename}.{extension}"

        self.duration = await self._get_video_metadata()
        self.thumb = await get_thumbnail(self.identifier, self.file_path, self.download_dir)
        
        if self.thumb and isinstance(self.thumb, str) and not await asyncio.to_thread(os.path.exists, self.thumb):
            try:
                logger.info(f"Thumbnail is a file_id. Downloading it to a local file: {self.thumb}")
                local_thumb_path = os.path.join(self.download_dir, "user_thumb.jpg")
                await self.client.download_media(self.thumb, file_name=local_thumb_path)
                self.thumb = local_thumb_path
            except Exception as e:
                logger.error(f"Failed to download thumbnail from file_id. Error: {e}")
                self.thumb = None

        self.file_size = os.path.getsize(self.file_path)
        self.file_size_mb = self.file_size / (1024 * 1024)

        self._prepare_progress_data()


    async def _get_video_metadata(self):
        duration = 0
        try:
            metadata = await asyncio.to_thread(extractMetadata, createParser(self.file_path))
            if metadata and metadata.has("duration"):
                duration = metadata.get('duration').seconds
        except Exception as e:
            logger.error(f"Error getting duration: {e}")
        return duration

    def _prepare_progress_data(self):
        """Initialize or get progress data for tracking upload."""
        self.progress_data = download_progress.get_task_progress(self.identifier) or {
            'video': {}, 'audio': {}, 'status': 'Upload',
            'platform': 'Unknown', 'filename': self.filename
        }

        self.content_info = self.progress_data.get('content_info', {})
        if not self.content_info:
            try:
                with open('data/content_storage.json', 'r') as f:
                    self.content_info = json.load(f).get(self.identifier, {})
            except Exception as e:
                logger.error(f"Failed to load content info from storage: {e}")

        self.progress_data['status'] = 'Upload'
        self.progress_data['upload'] = {
            'current_size': '0MB', 'total_size': f"{self.file_size_mb:.2f}MB",
            'speed': '0.00MB/s', 'eta': '00:00:00', 'percentage': 0
        }
        download_progress.update_progress(self.identifier, self.progress_data)

    async def _determine_upload_method(self):
        """Determine whether to use rclone or direct Telegram upload."""
        use_rclone_after_1990 = True
        force_drive_upload = self.content_info.get('force_drive_upload', False)

        if force_drive_upload: self.use_rclone = True
        elif self.file_size_mb > 3995: self.use_rclone = True
        elif self.file_size_mb > 1990 and use_rclone_after_1990: self.use_rclone = True
        elif self.file_size_mb > 1990:
            try:
                self.premium_client = await premium_session_pool.get_session()
                self.client = self.premium_client
                self.use_rclone = False
            except Exception as e:
                self.use_rclone = True
        else: self.use_rclone = False

    async def _upload_via_rclone(self):
        """Upload the video file using rclone to Google Drive."""
        drive = await get_available_drive(self.file_size_mb)
        config_file, drive_name = get_drive_config(drive)
        if not config_file or not drive_name:
            raise Exception(f"Failed to get configuration for drive {drive}")

        timestamp = str(int(time.time()))
        upload_path = f"uploads/{self.content_info.get('platform', 'Misc')}/{self.filename}_{timestamp}"
        
        success = await self._execute_rclone_upload(drive_name, config_file, upload_path)

        if success:
            drive_link = await self._get_drive_link(drive_name, config_file, upload_path)
            await self._send_drive_completion_message(drive_link)
        else:
            self.is_partial = True
            raise Exception("Rclone upload failed")

    async def _execute_rclone_upload(self, drive_name, config_file, upload_path):
        """Execute the rclone upload command and monitor progress."""
        start_time = time.time()
        
        async def rclone_progress(current, total):
            if not self.identifier: return
            
            percentage = (current * 100.0) / total if total > 0 else 0
            time_passed = max(0.1, time.time() - start_time)
            speed = current / time_passed
            eta_seconds = (total - current) / speed if speed > 0 else 0

            self.progress_data['upload'].update({
                'current_size': f"{current / (1024*1024):.2f}MB",
                'total_size': f"{total / (1024*1024):.2f}MB",
                'speed': f"{speed / (1024*1024):.2f}MB/s",
                'percentage': percentage,
                'eta': str(timedelta(seconds=int(eta_seconds)))
            })
            download_progress.update_progress(self.identifier, self.progress_data)

        rclone_cmd = [
            'rclone', 'copy', '--progress', '--transfers', '128', '--checkers', '64',
            '--buffer-size', '128M', '--drive-chunk-size', '256M', '--drive-upload-cutoff', '1000G',
            '--drive-pacer-min-sleep', '1ms', '--drive-pacer-burst', '2000',
            '--drive-acknowledge-abuse', '--retries-sleep', '1ms', '--low-level-retries', '20',
            '--multi-thread-streams', '32', '--stats', '1s', '--config', config_file,
            self.file_path, f'{drive_name}:{upload_path}'
        ]
        
        process = await asyncio.create_subprocess_exec(*rclone_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        
        total_size_bytes = self.file_size
        while True:
            line = await process.stdout.readline()
            if not line: break
            line_str = line.decode().strip()
            match = re.search(r"Transferred:\s+([\d\.]+\s*\w+)", line_str)
            if match:
                size_str = match.group(1).replace(" ", "")
                value = float(re.findall(r"[\d\.]+", size_str)[0])
                unit = re.findall(r"[a-zA-Z]+", size_str)[0]
                multipliers = {'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3, 'B': 1}
                current_size = value * multipliers.get(unit, 1)
                await rclone_progress(current_size, total_size_bytes)
        
        await process.wait()
        return process.returncode == 0

    async def _get_drive_link(self, drive_name, config_file, upload_path):
        """Get the Google Drive link for the uploaded file."""
        original_filename = os.path.basename(self.file_path)
        link_cmd = ['rclone', 'link', '--config', config_file, f'{drive_name}:{os.path.join(upload_path, original_filename)}']
        
        process = await asyncio.create_subprocess_exec(*link_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        link_output, _ = await process.communicate()
        return link_output.decode().strip() if link_output else None

    async def _send_drive_completion_message(self, drive_link):
        """Create and send completion message with Drive link."""
        file_size_str = f"{self.file_size_mb:.2f}MB"
        basic_details_msg = f"**{self.display_filename}**"
        channel_details_msg = f"**{self.display_filename}**"
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Drive Link", url=drive_link)]]) if drive_link else None

        try:
            await self.client.send_photo(self.channel_id, self.thumb, caption=channel_details_msg, reply_markup=buttons)
            self.uploaded_msg = await self.client.send_photo(self.chat_id, self.thumb, caption=basic_details_msg, reply_markup=buttons)
        except Exception:
            await self.client.send_message(self.channel_id, channel_details_msg, reply_markup=buttons)
            self.uploaded_msg = await self.client.send_message(self.chat_id, basic_details_msg, reply_markup=buttons)

    async def _upload_via_telegram(self):
        """Upload the video file directly to Telegram."""
        start_time = time.time()

        async def progress_callback(current, total):
            now = time.time()
            if now - getattr(progress_callback, 'last_update_time', 0) < 1: return
            progress_callback.last_update_time = now

            elapsed_time = now - start_time
            speed = current / elapsed_time if elapsed_time > 0 else 0
            eta = (total - current) / speed if speed > 0 else 0
            percentage = (current / total) * 100 if total > 0 else 0

            self.progress_data['upload'].update({
                'current_size': f"{current / (1024*1024):.2f}MB", 'total_size': f"{total / (1024*1024):.2f}MB",
                'speed': f"{speed / (1024*1024):.2f}MB/s", 'eta': str(timedelta(seconds=int(eta))), 'percentage': percentage
            })
            download_progress.update_progress(self.identifier, self.progress_data)
        
        caption = f"**{self.display_filename}**"
        await self._execute_telegram_upload(caption, progress_callback)

    async def _execute_telegram_upload(self, caption, progress_callback):
        """Execute the Telegram upload with retries."""
        max_retries, retry_count, last_error = 3, 0, None

        while retry_count < max_retries:
            try:
                shutil.copy2(self.file_path, self.display_filename)
                channel_caption = f"{caption}\n\n**👤 Uploader:** {self.user_mention}"

                with open(self.display_filename, 'rb') as video_file:
                    channel_msg = await self.client.send_document(
                        document=video_file, chat_id=self.channel_id, caption=channel_caption,
                        thumb=self.thumb, file_name=self.display_filename,
                        progress=progress_callback
                    )
                    self.uploaded_msg = await self.client.copy_message(
                        chat_id=self.chat_id, from_chat_id=channel_msg.chat.id,
                        message_id=channel_msg.id, caption=caption
                    )
                break
            except FloodWait as e:
                logger.warning(f"FloodWait error during upload: Waiting for {e.value} seconds.")
                await asyncio.sleep(e.value + 5)
                # We don't increment retry_count for FloodWait, just wait and retry.
                continue
            except Exception as e:
                retry_count += 1
                last_error = e
                logger.error(f"Upload attempt {retry_count} failed: {e}")
                if self.premium_client:
                    try:
                        await premium_session_pool.release_session(self.premium_client)
                        self.premium_client = await premium_session_pool.get_session()
                        self.client = self.premium_client
                    except Exception as se:
                        logger.error(f"Failed to get new premium session: {se}")
                await asyncio.sleep(5 * retry_count)
            if retry_count >= max_retries: raise last_error

    async def _send_completion_message(self):
        """Send completion status message after successful upload."""
        status_type = "upload_complete_drive" if self.use_rclone else "upload_complete_telegram"
        extra_data = {'uploaded_msg_id': self.uploaded_msg.id}
        
        if self.is_trial:
            try:
                with open('data/user_plans.json', 'r') as f: user_plans = json.load(f)
                res = self.progress_data.get('video', {}).get('resolution', '')
                height = int(res.split('x')[1]) if res and 'x' in res else 0
                limit_type = "720p" if height <= 720 else "1080p"
                extra_data.update({
                    'limit_type': limit_type,
                    'limit': user_plans.get(self.user_id, {}).get(f'{limit_type}_limit', 0)
                })
            except Exception as e: logger.error(f"Failed to handle user plans: {e}")

        # Use the direct progress_msg for final status update
        if self.progress_msg:
             await send_status_update(self.client, self.message, self.identifier, self.content_info, status_type, extra_data, self.progress_msg)
        else: # Fallback
             await send_status_update(self.client, self.message, self.identifier, self.content_info, status_type, extra_data)


    async def _handle_upload_failure(self, error):
        """Handle failure in upload process."""
        extra_data = {'error': str(error)}
        if self.is_trial:
            try:
                with open('data/user_plans.json', 'r+') as f:
                    user_plans = json.load(f)
                    res = self.progress_data.get('video', {}).get('resolution', '')
                    height = int(res.split('x')[1]) if res and 'x' in res else 0
                    limit_type = "720p" if height <= 720 else "1080p"
                    
                    user_id_str = self.identifier.split('_')[0]
                    if user_id_str not in user_plans: user_plans[user_id_str] = {"720p_limit": 0, "1080p_limit": 0}
                    user_plans[user_id_str][f"{limit_type}_limit"] += 1
                    
                    f.seek(0)
                    json.dump(user_plans, f, indent=4)
                    f.truncate()
                    
                    extra_data.update({
                        'limit_type': limit_type,
                        'limit': user_plans[user_id_str][f'{limit_type}_limit']
                    })
                
                if int(user_id_str) in TRIAL_COOLDOWNS:
                    TRIAL_COOLDOWNS[int(user_id_str)]["time"] = time.time() + TRIAL_COOLDOWN_FAIL
            except Exception as e: logger.error(f"Failed to restore task limit: {e}")
        
        if self.progress_msg:
            await self.progress_msg.edit_text(f"❌ **Upload Failed:**\n`{str(error)}`")
        else:
            await send_status_update(self.client, self.message, self.identifier, self.content_info, "upload_unsuccessful", extra_data)

    async def _cleanup(self):
        """Clean up resources after upload."""
        await cleanup_resources(self.thumb, self.download_dir, self.display_filename)
        download_progress.clear_task(self.identifier)
        try: await self.message.delete()
        except Exception: pass

    async def _finalize(self):
        """Finalize the upload process and release resources."""
        if self.premium_client:
            try: await premium_session_pool.release_session(self.premium_client)
            except Exception as e: logger.error(f"Error releasing premium session: {e}")
        
        await self._cleanup()

async def upload_video(client, message, file_path, filename, download_dir, identifier, progress_msg=None):
    """Upload video file to telegram with proper metadata."""
    uploader = VideoUploader(client, message, file_path, filename, download_dir, identifier, progress_msg)
    return await uploader.upload()


async def handle_amazon(client, message, url):
    """
    Handle Amazon Prime Video URLs by fetching content info and returning structured data
    """
    if not url.startswith(("https://www.primevideo.com", "https://primevideo.com", "https://www.amazon.com/gp/video")):
        return None

    async def amazon_task():
        try:
            # Auto-select option 3: CBR H.264
            mpd_choice = "3"

            if USE_AMAZON_API_ENDPOINT:
                format_path = "264" if USE_AMAZON_264 else "265"
                api_url = f"{AMAZON_API_ENDPOINT}/{format_path}/{url}?mpd_choice={mpd_choice}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url) as response:
                        if response.status != 200:
                            logger.error(f"Amazon API error: Status {response.status}")
                            return None
                        result_info = await response.json()
            else:
                result_info = await amzn.fetch_gti_from_url(url, mpd_choice)

            info = {
                "content_url": result_info["content_url"], "platform": result_info["platform"],
                "title": result_info["title"], "content_type": result_info["content_type"],
                "episode_title": result_info["episode_title"], "episode_number": result_info["episode_number"],
                "content_id": result_info["content_id"], "thumbnail": result_info["thumbnail"],
                "streams": {"dash": result_info["streams"]["dash"], "hls": result_info["streams"]["hls"]},
                "drm": {"needs_decryption": result_info["drm"]["needs_decryption"], "license_url": result_info["drm"]["license_url"], "keys": result_info["drm"]["keys"]},
                "subtitles": result_info.get("subtitles", [])
            }

            formats = await get_formats(info)
            if formats:
                info["streams_info"] = formats["streams"]
            else:
                info["streams_info"] = {'video': [], 'audio': [], 'subtitles': []}
            logger.info("Successfully processed Amazon Prime URL and returning info")
            return info
        except Exception as e:
            logger.error(f"Amazon Prime error: {str(e)}")
            return None

    return await amazon_task()

async def check_subscription(message):
    """Check if user is subscribed to main channel and has access"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id

        # First check if user has access (either user or chat)
        has_access = (user_id in get_full_access_users()) or (user_id in TRIAL_ACCESS) or (chat_id in get_full_access_users()) or (chat_id in TRIAL_ACCESS)
        if not has_access:
            buttons = [[InlineKeyboardButton("Get Access", url=f"https://t.me/{OWNER}")],]
            await message.reply(
                "🔒 **Access Denied**\n\n"
                "You do not have permission to use this bot. Please contact the bot owner for access.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return False

        # Then check channel subscription
        member = None
        try:
            member = await app.get_chat_member(MAIN_CHANNEL, user_id)
        except Exception:
            pass

        if member and (member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]):
            return True

        buttons = [
            [InlineKeyboardButton("🎬 Join Our Channel", url=f"https://t.me/{OWNER_CHANNEL}")],
            [InlineKeyboardButton("✨ Let's Start", callback_data=f"check_{user_id}")]
        ]
        await message.reply(
            "✨ **Join Our Channel!**\n\n"
            "To use this bot, you must be a member of our channel. Please join using the button below, then come back and press 'Let's Start'.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return False
    except Exception:
        return False

async def handle_hotstar(client, message, url):
    if not url.startswith(("https://www.hotstar.com", "https://hotstar.com")):
        return None

    async def show_language_selection(content_id, sport_type):
        """Handle language selection UI and user interaction for sports content"""
        # Make initial request to get available languages
        initial_url = f"{hotstar.BASE_URL}/sports/{sport_type}/dummy/{content_id}/watch"
        try:
            initial_response = await hotstar.make_request(initial_url, headers=hotstar.HEADERS)
            player_data = initial_response.get("success", {}).get("page", {}).get("spaces", {}).get("player", {}).get("widget_wrappers", [{}])[0].get("widget", {}).get("data", {})
            available_languages = player_data.get("player_config", {}).get("content_metadata", {}).get("audio_languages", [])

            # Default language options when API doesn't return any
            default_languages = [
                {"name": "Hindi", "iso3code": "hin"},
                {"name": "English", "iso3code": "eng"},
                {"name": "Tamil", "iso3code": "tam"},
                {"name": "Telugu", "iso3code": "tel"},
                {"name": "Bengali", "iso3code": "ben"},
                {"name": "Malayalam", "iso3code": "mal"},
                {"name": "Kannada", "iso3code": "kan"},
                {"name": "Marathi", "iso3code": "mar"}
            ]

            if not available_languages:
                available_languages = default_languages
                logger.info("Using default language options as API returned none")

            language_text = "**🌐 Available Languages:**\n\n" + "\n".join(
                f"**{i}.** `{lang['name']}`"
                for i, lang in enumerate(available_languages, 1)
            ) + "\n\n**⏰ Enter the number of your choice (60s timeout)**"

            lang_msg = await message.reply_text(language_text)

            try:
                response = await client.wait_for_message(
                    chat_id=message.chat.id,
                    filters=filters.create(lambda _, __, m: (
                        m.from_user and m.from_user.id == message.from_user.id and m.text and m.text.isdigit()
                    )),
                    timeout=60
                )

                try:
                    choice = int(response.text)
                    if not 1 <= choice <= len(available_languages):
                        await lang_msg.delete()
                        await response.delete()
                        await message.reply_text("Invalid choice!")
                        return None, None

                    selected_language = available_languages[choice - 1]
                    selected_code = selected_language['iso3code'].lower()
                    selected_name = selected_language['name']

                    await lang_msg.delete()
                    await response.delete()

                    confirm_msg = await message.reply_text(f"Selected: {selected_name}")
                    await asyncio.sleep(3)
                    await confirm_msg.delete()

                    return selected_code, selected_name

                except ValueError:
                    await lang_msg.delete()
                    await response.delete()
                    await message.reply_text("Please enter a valid number!")
                    return None, None

            except asyncio.TimeoutError:
                await lang_msg.delete()
                await message.reply_text("Language selection timed out!")
                return None, None

        except Exception as e:
            logger.error(f"Error fetching languages: {str(e)}")
            await message.reply_text("Failed to fetch available languages!")
            return None, None

    async def hotstar_task():
        try:
            # Import the hotstar module
            # Check if it's sports content that needs language selection
            language = None
            selected_language_name = None

            if "/sports/" in url:
                # Extract content ID and sport type for language selection
                parts = url.replace("/in/", "/").replace("https://www.hotstar.com/", "").strip("/").split("/")
                sport_type = parts[0]
                content_id = parts[-4] if "video/highlights/watch" in url or "video/replay/watch" in url else parts[-2]

                # Get language selection through UI
                language, selected_language_name = await show_language_selection(content_id, sport_type)
                if not language:
                    return None

            # Now call the hotstar main function with the URL and selected language
            result_info = await hotstar.main(url, language, selected_language_name)

            if not result_info:
                logger.error("Failed to retrieve information from Hotstar")
                return None

            # result_info already has our standardized structure, so we can use it directly
            info = result_info

            # Get formats information if needed
            formats = await get_formats(info)
            if formats:
                info["streams_info"] = formats["streams"]
                logger.info("Successfully retrieved format information for Hotstar")
            else:
                logger.warning("Failed to retrieve format information for Hotstar")

            logger.info("Successfully processed Hotstar URL and returning info")
            return info

        except Exception as e:
            logger.error(f"Hotstar error: {str(e)}")
            return None

    # Create task for Hotstar processing
    task = asyncio.create_task(hotstar_task())  # Create task immediately
    return task  # Return the created task



async def get_platform_content(client, message, platform, url):
    """Get content details based on platform"""
    try:
        handlers = {
            "ZEE5": handle_zee,
            "MXPlayer": handle_mxplayer,
            "Aha": handle_aha,
            "SunNXT": handle_sunnxt,
            "SonyLIV": handle_sonyliv,
            "JioHotstar": handle_hotstar,
            "Amazon Prime": handle_amazon,
            "Discovery+": handle_dplus,
        }
        platform_map = {
            "-zee": "ZEE5",
            "-mxp": "MXPlayer",
            "-aha": "Aha",
            "-sunxt": "SunNXT",
            "-sony": "SonyLIV",
            "SonyLIV": "SonyLIV",
            "ZEE5": "ZEE5",
            "MXPlayer": "MXPlayer",
            "Aha": "Aha",
            "SunNXT": "SunNXT",
            "-jstar": "JioHotstar",
            "JioHotstar": "JioHotstar",
            "-amzn": "Amazon Prime",
            "Amazon Prime": "Amazon Prime",
            "-dplus": "Discovery+",
            "Discovery+": "Discovery+",
        }

        logger.info(f"Processing URL: {url} with platform flag: {platform}")

        if platform not in platform_map:
            logger.error(f"Invalid platform flag: {platform}")
            error_msg = await message.reply("❌ **Invalid platform specified**")
            await asyncio.sleep(3)
            await error_msg.delete()
            return None

        platform_name = platform_map[platform]
        handler = handlers[platform_name]
        logger.info(f"Using handler for platform: {platform_name}")

        # Create task with timeout
        try:
            async with asyncio.timeout(120):  # 2 minute timeout
                # Run handler in task to prevent blocking
                task = asyncio.create_task(handler(client, message, url))
                content_info = await task
        except asyncio.TimeoutError:
            logger.error(f"Handler {platform_name} timed out for URL: {url}")
            await message.reply(f"❌ Request timed out while processing {platform_name}")
            return None
        except Exception as e:
            logger.error(f"Error in handler {platform_name}: {str(e)}")
            return None

        if content_info is None:
            logger.error(f"Handler {platform_name} returned None for URL: {url}")
        else:
            logger.info(f"Successfully retrieved content info for {platform_name}")

        return content_info

    except Exception as e:
        logger.exception(f"Error in get_platform_content: {str(e)}")
        return None

COMMAND_MAP = {
    "zee": "-zee",
    "sunxt": "-sunxt",
    "mxp": "-mxp",
    "dplus": "-dplus",
    "sliv": "-sony",
    "jstar": "-jstar",
    "amzn": "-amzn",
    "aha": "-aha",
}

@app.on_message(filters.command("setthumb"))
async def set_thumbnail_command(client, message):
    """Sets a custom thumbnail for the user."""
    reply = message.reply_to_message
    if not reply or not reply.photo:
        await message.reply_text("Please reply to a photo to set it as your custom thumbnail.")
        return

    user_id = message.from_user.id
    thumb_id = reply.photo.file_id
    
    try:
        await thumb_db.update_one(
            {"_id": user_id},
            {"$set": {"thumb_id": thumb_id}},
            upsert=True
        )
        await message.reply_text("✅ **Custom thumbnail has been set successfully!**")
    except Exception as e:
        logger.error(f"Failed to set thumbnail for user {user_id}: {e}")
        await message.reply_text("❌ Failed to set thumbnail. Please try again later.")

@app.on_message(filters.command("delthumb"))
async def delete_thumbnail_command(client, message):
    """Deletes the user's custom thumbnail."""
    user_id = message.from_user.id
    try:
        result = await thumb_db.delete_one({"_id": user_id})
        
        if result.deleted_count:
            await message.reply_text("✅ **Your custom thumbnail has been deleted.**")
        else:
            await message.reply_text("ℹ️ You don't have a custom thumbnail set.")
    except Exception as e:
        logger.error(f"Failed to delete thumbnail for user {user_id}: {e}")
        await message.reply_text("❌ Failed to delete thumbnail. Please try again later.")

@app.on_message(filters.command("showthumb"))
async def show_thumbnail_command(client, message):
    """Shows the user's current custom thumbnail."""
    user_id = message.from_user.id
    try:
        user_thumb = await thumb_db.find_one({"_id": user_id})
        
        if user_thumb and user_thumb.get("thumb_id"):
            await client.send_photo(
                chat_id=message.chat.id,
                photo=user_thumb["thumb_id"],
                caption="This is your current custom thumbnail."
            )
        else:
            await message.reply_text("ℹ️ You don't have a custom thumbnail set. Use `/setthumb` by replying to a photo.")
    except Exception as e:
        logger.error(f"Failed to show thumbnail for user {user_id}: {e}")
        await message.reply_text("❌ Failed to show thumbnail. Please try again later.")

@app.on_message(filters.command(list(COMMAND_MAP.keys())) & filters.chat(ALLOWED_ID))
async def unified_command_handler(client, message):
    try:
        if is_bot_locked():
            await message.reply(LOCK_MESSAGE)
            return


        command = message.command[0].lower()
        platform_flag = COMMAND_MAP.get(command)

        # Create task with cancellation support
        task = asyncio.create_task(process_dl_request(client, message, platform_flag))
        try:
            await asyncio.wait_for(task, 300)  # 5 minute total timeout
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.warning(f"Task for /{command} was cancelled due to timeout")
                await message.reply("**Request timed out. Please try again later.**")
        except Exception as e:
            logger.error(f"Error processing /{command} request: {e}")
            error_msg = await message.reply("**API did not respond. This issue is not from our end. Please try again after some time.**")
            await asyncio.sleep(5)
            await error_msg.delete()

    except Exception as e:
        logger.exception(f"Error in unified_command_handler: {str(e)}")
        error_msg = await message.reply(f"❌ Error: {str(e)}")
        await message.delete()
        await asyncio.sleep(5)
        await error_msg.delete()

async def process_dl_request(client, message, platform_flag):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        current_time = time.time()

        # Trial user check (existing code)
        is_trial = (user_id not in get_full_access_users() and chat_id not in get_full_access_users()) and (user_id in TRIAL_ACCESS or chat_id in TRIAL_ACCESS)
        if is_trial:
            # Check for restricted platforms first
            platform_name = PLATFORM_EXAMPLES.get(platform_flag, ["Unknown"])[0]
            if platform_name in TRIAL_RESTRICTED_PLATFORMS:
                await message.reply(
                    f"**⚠️ Access Restricted**\n\n"
                    f"**{TRIAL_RESTRICTED_PLATFORMS[platform_name]}**\n\n"
                    "**🌟 Upgrade to full access to use all platforms!**"
                )
                return

            if user_id in TRIAL_COOLDOWNS:
                cooldown_end = TRIAL_COOLDOWNS[user_id]["time"]
                if current_time < cooldown_end:
                    remaining = int(cooldown_end - current_time)
                    minutes = remaining // 60
                    seconds = remaining % 60
                    await message.reply(
                        f"**⏳ Please wait {minutes}m {seconds}s before starting another download.**\n"
                        "**🌟 Upgrade to full access to download without waiting!**"
                    )
                    return
                else:
                    del TRIAL_COOLDOWNS[user_id]

            # Only check task limits for trial users
            try:
                with open('data/user_plans.json', 'r') as f:
                    user_plans = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                user_plans = {}

            str_user_id = str(user_id)

            # Check if trial user has any tasks available
            has_720p = user_plans.get(str_user_id, {}).get("720p_limit", 0) > 0
            has_1080p = user_plans.get(str_user_id, {}).get("1080p_limit", 0) > 0

            if not has_720p and not has_1080p:
                verify_bot = ASSISTANT_BOT
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 Get Access", url=f"https.t.me/{verify_bot}?start=verify")]
                ])
                await message.reply(
                    "**No Tasks Available!**\n\n"
                    "Looks like you're all out of tasks. Time to get verified again.\n\n"
                    "**What You Can Do:**\n"
                    "• Click the button below to get more tasks\n"
                    "• Choose between 720p or 1080p\n"
                    "• Come back here once you're verified\n\n"
                    "Don't worry, the process is painless... mostly.",
                    reply_markup=keyboard
                )
                return

        # Continue with the rest of the dl command logic
        command_parts = message.text.split()

        # Check for ongoing downloads in the same platform for all users
        platform_name = PLATFORM_EXAMPLES.get(platform_flag, ["Unknown"])[0]
        if user_id not in OWNERS:
            has_reached_limit, reason = await check_download_limits(user_id, platform_name, chat_id)
            if has_reached_limit:
                # if reason == "platform_limit":
                #     await message.reply(
                #         f"**✨ You already have an ongoing task from {platform_name}. Please wait for it to complete.**"
                #     )
                #     return
                if reason == "max_concurrent":
                    await message.reply(
                        f"**✨ You have reached the maximum limit of 3 concurrent downloads. Please wait for at least one to complete.**"
                    )
                    return
                elif reason == "restricted_platform":
                    await message.reply(
                        f"**⚠️ Access Denied**\n\n"
                        f"**{platform_name} platform is restricted to authorized users only.**\n\n"
                        f"**Please contact an administrator if you need access.**"
                    )
                    return

        if len(command_parts) < 2:
            await message.reply(f"**Usage:** `/{message.command[0]} <URL> [-d]`")
            return

        # Check for flag to force drive upload
        force_drive_upload = "-d" in command_parts
        url = command_parts[1]

        # Send initial fetching message
        status_msg = await message.reply("🔍 **Fetching content information...**")

        # Run platform content fetch in executor to prevent blocking
        info = await get_platform_content(client, message, platform_flag, url)
        if not info:
            await status_msg.delete()
            error_msg = await message.reply(f"❌ Error: Failed to get content information")
            # Delete error message after 5 seconds
            await asyncio.sleep(5)
            await message.delete()
            await error_msg.delete()
            return

        # Update message with success and content info
        if isinstance(info, asyncio.Task):
            info = await info  # Properly await the task result

        # Double-check that info is still valid after awaiting task
        if not info:
            await status_msg.delete()
            error_msg = await message.reply(f"❌ Error: Failed to get content information")
            # Delete error message after 5 seconds
            await asyncio.sleep(5)
            await message.delete()
            await error_msg.delete()
            return

        # Add the force_drive_upload flag to info after confirming info is not None
        info["force_drive_upload"] = force_drive_upload

        platform = info.get('platform', 'Unknown')
        title = info.get('title', 'Unknown Title')
        episode_title = info.get('episode_title', '')
        episode_number = info.get('episode_number', '')

      #  text = f"**👤 User:** {message.from_user.mention}\n"
        text = f"**Title:** `{title}`"
        if episode_title:
            text += f"\n**Episode:** `{episode_title}`"
        if episode_number:
            text += f"\n**Episode Number:** `{episode_number}`"
        if force_drive_upload:
            text += f"\n**Upload Method:** `Drive (Forced)`"

        # Add available tasks info for trial users and resolution selection prompt together
        if is_trial:
            text += "\n\n**Available Tasks:**\n"
            if has_720p:
                text += f"• 720p Tasks: {user_plans[str(user_id)]['720p_limit']}\n"
            if has_1080p:
                text += f"• 1080p Tasks: {user_plans[str(user_id)]['1080p_limit']}"

        text += "**\n\nPlease select video resolution:**"

        await status_msg.edit_text(text)

        identifier = f"{message.from_user.id}_{message.id}"
        store_content_info(identifier, info)

        # Show resolution selection buttons and schedule deletion
        try:
            markup = create_resolution_buttons(identifier, info["streams_info"], info)
            await status_msg.edit_reply_markup(reply_markup=markup)
            asyncio.create_task(delete_buttons_after_delay(status_msg))
        except (KeyError, Exception) as e:
            # Log the error if it's an exception
            if isinstance(e, Exception):
                logger.exception(f"Error in process_dl_request: {str(e)}")

            # Handle the issue with a consistent approach
            info_msg = await message.reply("**Could not load streams. It's official API end issue, they didn't return any information. Not from our end.**")
            await asyncio.sleep(5)
            await message.delete()
            await info_msg.delete()
            if status_msg:
                await status_msg.delete()
    except Exception as e:
        logger.exception(f"Error in process_dl_request: {str(e)}")
        await message.reply(f"**Could not load streams. It's official API end issue, they didn't return any information. Not from our end.**")

@app.on_message(filters.command(["dtasks", "at"]))
async def show_tasks(_, message):
    if message.from_user.id not in OWNERS:
        await message.delete()
        return
        
    user_id = message.from_user.id
    chat_id = message.chat.id

    try: await message.delete()
    except Exception: pass

    if previous_msg := progress_display.active_task_messages.get(chat_id):
        try: await previous_msg.delete()
        except Exception: pass

    if not download_progress.tasks:
        status_msg = await message.reply_text(
            "**✨ No active downloads at the moment.**"
        )
        progress_display.active_task_messages[chat_id] = status_msg
        await asyncio.sleep(10)
        if progress_display.active_task_messages.get(chat_id) == status_msg:
            try: await status_msg.delete()
            except: pass
            progress_display.active_task_messages.pop(chat_id, None)
        return

    status_msg = await message.reply_text("`Fetching active tasks...`")
    progress_display.active_task_messages[chat_id] = status_msg

    async def update_progress():
        last_progress_text = None
        
        while progress_display.active_task_messages.get(chat_id) == status_msg:
            current_page = progress_display.user_pages.get(user_id, 1)
            progress_text, buttons = await progress_display.format_all_progress(download_progress, page=current_page)

            if not progress_text:
                await status_msg.edit_text("**✅ All downloads completed!**")
                await asyncio.sleep(10)
                if progress_display.active_task_messages.get(chat_id) == status_msg:
                    try: await status_msg.delete()
                    except: pass
                break
            
            if progress_text != last_progress_text:
                try:
                    await status_msg.edit_text(
                        progress_text,
                        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
                    )
                    last_progress_text = progress_text
                except MessageNotModified: pass
                except Exception as e:
                    if "message to edit not found" in str(e).lower():
                        break
                    logger.error(f"Error updating task progress: {e}")

            await asyncio.sleep(12) # FIX: Increased sleep time to prevent flood waits

    asyncio.create_task(update_progress())

@app.on_message(filters.command("cancel"))
async def cancel_task_command(client, message):
    """Cancels a running task by its ID."""
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply_text(
            "**Usage:** `/cancel <task_id>`\n"
            "Your task ID is in the format `user_id_message_id` from your original command message."
        )

    task_id = message.command[1]

    try:
        task_owner_id = int(task_id.split('_')[0])
        if user_id != task_owner_id and user_id not in OWNERS:
            return await message.reply_text("❌ You can only cancel your own tasks.")
    except (ValueError, IndexError):
        return await message.reply_text("❌ Invalid Task ID format.")

    task_data = download_progress.get_task_progress(task_id)
    if not task_data or 'main_task' not in task_data:
        return await message.reply_text("Task not found, already completed, or cannot be cancelled.")

    if task_data['main_task'].done():
        return await message.reply_text("Task has already finished.")
        
    task_data['main_task'].cancel()
    await message.reply_text(f"✅ Cancellation request sent for task `{task_id}`.")


async def update_user_task_progress(identifier, progress_msg):
    """A looping task to update a user's specific progress message."""
    last_text = ""
    while identifier in download_progress.tasks:
        progress_data = download_progress.get_task_progress(identifier)
        if not progress_data:
            break
            
        text = await progress_display.format_task_progress(identifier, progress_data)
        
        if text != last_text:
            try:
                buttons = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{identifier}")
                ]])
                await progress_msg.edit_text(text, reply_markup=buttons)
                last_text = text
            except MessageNotModified:
                pass
            except Exception as e:
                logger.warning(f"Failed to update progress for {identifier}, stopping updater: {e}")
                break 
        
        await asyncio.sleep(12) # FIX: Increased sleep time to prevent flood waits

@app.on_callback_query()
async def handle_callback(client, callback_query: CallbackQuery):
    try:
        current_user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id
        is_trial = (current_user_id not in get_full_access_users() and chat_id not in get_full_access_users()) and (current_user_id in TRIAL_ACCESS or chat_id in TRIAL_ACCESS)

        data = callback_query.data
        if not data:
            return

        # Handle cancellation button
        if data.startswith('cancel_'):
            identifier = data.replace('cancel_', '')
            task_owner_id = int(identifier.split('_')[0])

            if current_user_id != task_owner_id and current_user_id not in OWNERS:
                return await callback_query.answer("❌ This is not your task to cancel.", show_alert=True)
            
            task_data = download_progress.get_task_progress(identifier)
            if not task_data or 'main_task' not in task_data:
                return await callback_query.answer("Task not found or already completed.", show_alert=True)

            if task_data['main_task'].done():
                return await callback_query.answer("Task has already finished.", show_alert=True)

            task_data['main_task'].cancel()
            await callback_query.answer("Cancellation request sent.", show_alert=True)
            return

        # Handle subscription check callback
        if data.startswith('check_'):
            user_id = int(data.split('_')[1])
            if user_id != callback_query.from_user.id:
                await callback_query.answer("❌ This button is not for you!", show_alert=True)
                return

            try:
                member = await app.get_chat_member(MAIN_CHANNEL, user_id)

                if member.status == ChatMemberStatus.MEMBER or member.status == ChatMemberStatus.ADMINISTRATOR or member.status == ChatMemberStatus.OWNER:
                    await callback_query.message.edit(

                        "• Wait for your download\n\n"
                        "**📺 Supported Platforms:**\n"
                        + "\n".join([f"• Use `/{cmd}` for {PLATFORM_EXAMPLES[flag][0]}" for cmd, flag in COMMAND_MAP.items()]) + "\n\n"
                        "**🔥 Start downloading your favorite content now!**",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ Close", callback_data=f"close_{user_id}")]
                        ])
                    )
                    await callback_query.answer("✨ Welcome! You can now use the bot", show_alert=True)
                else:
                    await callback_query.answer("🎬 Please join our channel first to access the bot!", show_alert=True)
            except Exception:
                await callback_query.answer("🎬 Please try again in a few seconds!", show_alert=True)
            return

        # Handle close button callback
        if data.startswith('close_'):
            user_id = int(data.split('_')[1])
            if user_id != callback_query.from_user.id:
                await callback_query.answer("❌ This button is not for you!", show_alert=True)
                return
            await callback_query.message.delete()
            return

        # Handle pagination callbacks
        if data.startswith(('page_', 'refresh_')):
            try:
                user_id = callback_query.from_user.id
                page = int(data.split('_')[1]) if data.startswith('page_') else progress_display.user_pages.get(user_id, 1)
                progress_display.user_pages[user_id] = page

                progress_text, buttons = await progress_display.format_all_progress(download_progress, page)
                if progress_text:
                    await callback_query.message.edit_text(
                        progress_text,
                        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
                    )
                await callback_query.answer()
                return
            except Exception as e:
                logger.error(f"Error in pagination: {e}")
                await callback_query.answer("Error in pagination!", show_alert=True)
                return

        # Handle "Select All" and "Clear All" before the generic split to avoid parsing errors.
        if data.startswith('aud_all_') or data.startswith('aud_clear_'):
            parts = data.split('_')
            action_part = f"{parts[0]}_{parts[1]}"
            base_identifier = f"{parts[2]}_{parts[3]}"

            if callback_query.from_user.id != int(base_identifier.split('_')[0]):
                await callback_query.answer("Not Your Button!", show_alert=True)
                return

            callback_storage = load_callback_storage()
            try:
                with open('data/content_storage.json', 'r', encoding='utf-8') as f:
                    content_storage = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return await callback_query.answer("Content not found!")

            content_info = content_storage.get(base_identifier)
            if not content_info:
                return await callback_query.answer("Content not found!")

            if base_identifier not in callback_storage:
                callback_storage[base_identifier] = {"selected_audios": []}

            if action_part == "aud_all":
                all_audios = content_info["streams_info"].get("audio", [])
                if is_trial:
                    all_audios.sort(key=lambda x: -x.get("bitrate", 0))
                    selected_audios = [a["stream_id"] for a in all_audios[:2]]
                    await callback_query.answer("Selected top 2 audio tracks.", show_alert=True)
                else:
                    selected_audios = [a["stream_id"] for a in all_audios]
                    await callback_query.answer("Selected all audio tracks.")
                callback_storage[base_identifier]["selected_audios"] = selected_audios
            else:
                callback_storage[base_identifier]["selected_audios"] = []
                await callback_query.answer("Cleared audio selections.")

            save_callback_storage(callback_storage)
            markup = create_audio_buttons(base_identifier, content_info["streams_info"])
            try:
                await callback_query.message.edit_reply_markup(reply_markup=markup)
            except MessageNotModified: pass
            return

        # Parse callback data for other actions
        parts = data.split('_', 3)
        if len(parts) < 3: return

        action, user_id_str, msg_id_str = parts[0], parts[1], parts[2]
        base_identifier = f"{user_id_str}_{msg_id_str}"

        if callback_query.from_user.id != int(user_id_str):
            return await callback_query.answer("Not Your Button!", show_alert=True)
        
        callback_storage = load_callback_storage()
        try:
            with open('data/content_storage.json', 'r', encoding='utf-8') as f:
                content_info = json.load(f).get(base_identifier)
        except (FileNotFoundError, json.JSONDecodeError):
            content_info = None

        if not content_info: return await callback_query.answer("Content not found!")

        if base_identifier not in callback_storage:
            callback_storage[base_identifier] = {"selected_resolution": None, "selected_audios": []}

        if action == "res":
            if len(parts) < 4: return
            short_stream_id = parts[3]
            
            selected_video = next((v for v in content_info["streams_info"]["video"] if v["stream_id"] == short_stream_id or v["stream_id"].endswith(f"_{short_stream_id}")), None)
            
            if not selected_video: return

            is_tmdb = content_info.get("platform") == "TMDB"
            if is_tmdb:
                callback_storage[base_identifier]["selected_resolution"] = selected_video
                save_callback_storage(callback_storage)
                display_name = selected_video.get("display_name", "Unknown quality")
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Back", callback_data=f"back_{base_identifier}"), InlineKeyboardButton("Proceed ➡️", callback_data=f"proc_{base_identifier}")],
                    [InlineKeyboardButton("❌ Close", callback_data=f"close_{base_identifier}")]
                ])
                await callback_query.message.edit_text(
                    f"**Title:** `{content_info.get('title', 'Unknown')}`\n"
                    f"**Selected Quality:** `{display_name}`\n\n"
                    "**Click Proceed to Download →**",
                    reply_markup=markup
                )
                await callback_query.answer(f"Selected: {display_name}")
                return

            height = int(selected_video["resolution"].split("x")[1])
            if is_trial:
                try:
                    with open('data/user_plans.json', 'r') as f: user_plans = json.load(f)
                except (FileNotFoundError, json.JSONDecodeError): user_plans = {}
                
                limit_type = "720p" if height <= 720 else "1080p"
                if user_plans.get(user_id_str, {}).get(f"{limit_type}_limit", 0) <= 0:
                    return await callback_query.answer(f"No {limit_type} tasks left!", show_alert=True)
                if height > 1080:
                    return await callback_query.answer("Upgrade to full access for 4K!", show_alert=True)

            callback_storage[base_identifier]["selected_resolution"] = {k: selected_video[k] for k in ["stream_id", "resolution", "bitrate"]}
            save_callback_storage(callback_storage)
            markup = create_audio_buttons(base_identifier, content_info["streams_info"])
            await callback_query.message.edit_text("**🎧 Select One Or More Audio Tracks**", reply_markup=markup)
            await callback_query.answer()

        elif action == "back":
            callback_storage[base_identifier]["selected_audios"] = []
            save_callback_storage(callback_storage)
            markup = create_resolution_buttons(base_identifier, content_info["streams_info"], content_info)
            text = f"**Title:** `{content_info.get('title', 'N/A')}`\n\nPlease select video resolution:"
            await callback_query.message.edit_text(text, reply_markup=markup)
            await callback_query.answer()

        elif action == "aud":
            if len(parts) < 4: return
            stream_index = parts[3]
            stream_id_map = callback_storage[base_identifier].get("stream_id_map", {})
            matched_stream_id = stream_id_map.get(stream_index)
            if not matched_stream_id: return await callback_query.answer("Audio track not found!", show_alert=True)

            selected_audios = callback_storage[base_identifier].get("selected_audios", [])
            if is_trial and matched_stream_id not in selected_audios and len(selected_audios) >= 2:
                return await callback_query.answer("Upgrade for more than 2 audio tracks!", show_alert=True)

            if matched_stream_id in selected_audios: selected_audios.remove(matched_stream_id)
            else: selected_audios.append(matched_stream_id)
            callback_storage[base_identifier]["selected_audios"] = selected_audios
            save_callback_storage(callback_storage)
            
            markup = create_audio_buttons(base_identifier, content_info["streams_info"])
            try:
                await callback_query.message.edit_reply_markup(reply_markup=markup)
            except MessageNotModified: pass
            await callback_query.answer()

        elif action == "proc":
            if is_bot_locked():
                return await callback_query.answer("Bot is locked by admin.", show_alert=True)
            
            selected = callback_storage.get(base_identifier, {})
            if not selected.get("selected_resolution"): return await callback_query.answer("Select resolution first!")
            if not selected.get("selected_audios") and not content_info.get("platform") == "TMDB": return await callback_query.answer("Select audio first!")

            if base_identifier in download_progress.tasks:
                return await callback_query.answer("This task is already in progress.", show_alert=True)
            
            if is_trial:
                if current_user_id in TRIAL_COOLDOWNS and time.time() < TRIAL_COOLDOWNS[current_user_id]["time"]:
                    remaining = int(TRIAL_COOLDOWNS[current_user_id]["time"] - time.time())
                    return await callback_query.answer(f"Please wait {remaining//60}m {remaining%60}s!", show_alert=True)
                
                with open('data/user_plans.json', 'r+') as f:
                    user_plans = json.load(f)
                    height = int(selected["selected_resolution"]["resolution"].split("x")[1])
                    limit_type = "720p" if height <= 720 else "1080p"
                    if user_plans.get(user_id_str, {}).get(f"{limit_type}_limit", 0) <= 0:
                        return await callback_query.answer(f"No {limit_type} tasks left!", show_alert=True)
                    user_plans[user_id_str][f"{limit_type}_limit"] -= 1
                    f.seek(0); json.dump(user_plans, f, indent=4); f.truncate()
                
                TRIAL_COOLDOWNS[current_user_id] = {"time": time.time() + TRIAL_COOLDOWN_SUCCESS, "message_id": callback_query.message.id}
            
            await callback_query.answer("Starting download...")
            await callback_query.message.delete()
            
            progress_msg = await client.send_message(
                chat_id=callback_query.message.chat.id,
                text="`Preparing your download...`"
            )

            main_task = asyncio.create_task(
                handle_proceed_download(client, callback_query.message, content_info, selected["selected_resolution"], selected.get("selected_audios", []), base_identifier, progress_msg)
            )

            updater_task = asyncio.create_task(
                update_user_task_progress(base_identifier, progress_msg)
            )

            initial_progress_data = {
                'main_task': main_task,
                'updater_task': updater_task,
                'status': 'Download',
                'platform': content_info.get("platform"),
                'filename': construct_filename(content_info, base_identifier),
                'content_info': content_info,
                'video': {}, 'audio': {}, 'upload': {}
            }
            download_progress.update_progress(base_identifier, initial_progress_data)


    except MessageNotModified: pass
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        try: await callback_query.answer("An error occurred!", show_alert=True)
        except Exception: pass


async def delete_buttons_after_delay(message, delay=600):  # 600 seconds = 10 minutes
    """Delete entire message after specified delay."""
    await asyncio.sleep(delay)
    try:
       await message.delete()
    except Exception:
       pass


async def scheduled_drive_cleanup():
    logger.info("Starting scheduled drive cleanup task")
    while True:
        try:
            logger.info("Running scheduled drive cleanup")
            await cleanup_old_files()
            logger.info("Scheduled drive cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error in scheduled drive cleanup: {str(e)}")
        # Wait for 10 minutes before next cleanup
        await asyncio.sleep(600)  # 10 minutes

async def main():
    """Main entry point for the bot."""
    max_retries = 5
    retry_delay = 5
    retry_count = 0

    while retry_count < max_retries:
        try:
            await app.start()
            logger.info("Bot Started Successfully!")

            # Start the scheduled drive cleanup as a background task
            cleanup_task = asyncio.create_task(scheduled_drive_cleanup())
            # Start periodic dump cleanup as a background task
            asyncio.create_task(periodic_dump_cleanup())

            # Reset retry count on successful connection
            retry_count = 0

            await idle()  # Keep the bot running
            break  # Exit the loop if idle() completes normally

        except ConnectionError as e:
            retry_count += 1
            logger.warning(f"Connection error (attempt {retry_count}/{max_retries}): {str(e)}")
            if retry_count < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("Max retries reached. Shutting down.")
                break

        except KeyboardInterrupt:
            logger.warning("Received KeyboardInterrupt")
            break

        except Exception as e:
            logger.error(f"Unexpected error in main(): {str(e)}")
            break

        finally:
            try:
                # First stop premium sessions
                await premium_session_pool.close_all_sessions()
                # Then stop the main app
                await app.stop()
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")

def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    logger.info(f"Received signal {signum}")
    loop = asyncio.get_event_loop()

    async def cleanup():
        # Cancel all tasks first
        try:
            # Get all tasks except current
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

            # Cancel all tasks
            for task in tasks:
                task.cancel()

            # Wait for all tasks to complete with a timeout
            await asyncio.wait(tasks, timeout=5.0)

            # Close any remaining resources
            await premium_session_pool.close_all_sessions()

        except asyncio.TimeoutError:
            logger.warning("Some tasks did not complete in time during cleanup")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

    try:
        # Run cleanup
        loop.run_until_complete(cleanup())
    except Exception as e:
        logger.error(f"Error during signal handler cleanup: {str(e)}")
    finally:
        try:
            # Get all pending tasks
            pending = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]

            # Cancel any remaining tasks
            for task in pending:
                task.cancel()

            # Wait with a timeout
            loop.run_until_complete(asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=5.0
            ))
        except asyncio.TimeoutError:
            logger.warning("Some tasks did not complete in time during shutdown")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
            except Exception as e:
                logger.error(f"Error closing loop: {str(e)}")

premium_session_pool = PremiumSessionPool(PREMIUM_STRING)

async def check_download_limits(user_id, platform_name=None, chat_id=None):
    # Check for global lock
    if is_bot_locked():
        return True, "bot_locked"
    # Define platforms with special concurrent download limits
    SPECIAL_PLATFORM_LIMITS = {
        "TMDB": 3  # Allow up to 3 concurrent downloads for TMDB
    }

    # Check if user is trying to use TataPlay and doesn't have permission
    if platform_name == "TataPlay" and user_id not in OWNERS and user_id not in TATAPLAY_USER and (chat_id is None or chat_id not in TATAPLAY_USER):
        return True, "restricted_platform"

    # Only check for platforms in TRIAL_RESTRICTED_PLATFORMS or SPECIAL_PLATFORM_LIMITS
    if platform_name not in TRIAL_RESTRICTED_PLATFORMS and platform_name not in SPECIAL_PLATFORM_LIMITS:
        return False, ""

    # Count total downloads for this user
    total_downloads = 0
    platform_downloads = {}

    # Check in the download_progress tracker
    try:
        for identifier, progress_data in download_progress.tasks.items():
            try:
                # Extract user ID from first half of identifier
                stored_user_id = int(identifier.split('_')[0])
                if stored_user_id != user_id:
                    continue

                # Increment total downloads counter
                total_downloads += 1

                # If platform name is provided, check for that specific platform
                if platform_name:
                    try:
                        with open('data/content_storage.json', 'r', encoding='utf-8') as f:
                            storage = json.load(f)

                        if identifier in storage:
                            stored_platform = storage[identifier].get('platform')
                            # Check if the status is download, upload or post-processing
                            real_status = await progress_display.get_real_status(progress_data)
                            if real_status in ['Download', 'Post Processing', 'Upload']:
                                if stored_platform not in platform_downloads:
                                    platform_downloads[stored_platform] = 0
                                platform_downloads[stored_platform] += 1

                                if stored_platform == platform_name:
                                    logger.info(f"User {user_id} already has {real_status} for {platform_name}: {identifier}")
                    except (FileNotFoundError, json.JSONDecodeError):
                        pass

            except (ValueError, AttributeError, IndexError):
                continue
    except Exception as e:
        logger.error(f"Error checking download limits: {str(e)}")

    # Check if total downloads limit is reached
    if total_downloads >= 3:
        return True, "max_concurrent"

    # Check platform-specific limits
    if platform_name in SPECIAL_PLATFORM_LIMITS:
        max_allowed = SPECIAL_PLATFORM_LIMITS[platform_name]
        current_count = platform_downloads.get(platform_name, 0)
        if current_count >= max_allowed:
            return True, "platform_limit"
    elif platform_name in TRIAL_RESTRICTED_PLATFORMS and platform_downloads.get(platform_name, 0) > 0:
        return True, "platform_limit"

    return False, ""

if __name__ == "__main__":
    # Set up signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, signal_handler)

    # Run the bot using asyncio
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        try:
            # Get all pending tasks
            pending = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
            # Wait with a timeout
            loop.run_until_complete(asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=5.0
            ))
        except asyncio.TimeoutError:
            logger.warning("Some tasks did not complete in time during shutdown")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
            except Exception as e:
                logger.error(f"Error closing loop: {str(e)}")
