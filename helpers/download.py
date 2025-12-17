
import asyncio
import glob
import os
import re
import logging
from qbittorrent import Client # type: ignore
import time
import shutil
import json

# Get logger
logger = logging.getLogger(__name__)

# These will be imported at runtime from the main module
download_progress = None
progress_display = None

# Import constants
from hotstar import mpd_hotstar_headers
from sonyliv_api import mpd_headers as sonyliv_mpd_headers

from helpers.config import USE_PROXY, MP4_USER_IDS, PROXY_URL, DUMP_STREAMS

PROXY_URL1 = "http://143.110.189.252:9076"
    
class BaseDownloader:
    """Base class for downloaders with common functionality."""
    def __init__(self, stream_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier):
        self.stream_url = stream_url
        self.selected_resolution = selected_resolution
        self.selected_audios = selected_audios
        self.content_info = content_info
        self.download_dir = download_dir
        self.filename = filename
        self.identifier = identifier
        self.processes = []
        self.progress_data = None
        self.enable_logging = True
        self.needs_decryption = content_info.get("drm", {}).get("needs_decryption", False)
        self.final_merged_path = None
        self.last_progress_update_time = 0

    async def _merge_streams(self, video_path, audio_paths, output_path):
        """Merge downloaded streams using ffmpeg."""
        input_args = ['-i', video_path]
        map_args = ['-map', '0:v']

        # Handle audio paths if they exist
        if audio_paths:
            for i, audio_path in enumerate(audio_paths):
                input_args.extend(['-i', audio_path])
                map_args.extend(['-map', f'{i+1}:a'])
        else:
            # If no audio paths, map all audio streams from video file
            map_args.extend(['-map', '0:a'])
        
        # Map all subtitle streams
        map_args.extend(['-map', '0:s?'])

        # Get user_id to determine if we should use MP4 format
        user_id = self.identifier.split('_')[0] if '_' in self.identifier else None
        use_mp4 = user_id in MP4_USER_IDS
        
        cmd = [
            'ffmpeg', '-y',
            *input_args,
            *map_args,
            '-c', 'copy',
        ]
        
        # Add specific format options if using MP4
        if use_mp4 and output_path.endswith('.mp4'):
            cmd.extend(['-f', 'mp4'])
        
        cmd.append(output_path)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"FFmpeg merge failed with return code {process.returncode}")

    async def _cleanup(self, files):
        """Clean up temporary files."""
        logger.info("Cleaning up temporary files...")
        for f in files:
            try:
                if os.path.exists(f):
                    os.remove(f)
                    logger.info(f"Removed temporary file: {f}")
            except Exception as e:
                logger.error(f"Error cleaning up {f}: {e}")

    async def _find_files(self, pattern_list):
        """Find files matching any of the given patterns."""
        found_files = []
        for pattern in pattern_list:
            found_files.extend(glob.glob(pattern))
        return found_files

    async def _check_and_delete_existing_files(self):
        """Check and delete any existing video or audio files with the same name"""
        try:
            # Check for existing files with similar names
            base_path = os.path.join(self.download_dir, self.filename)
            
            # Common video and audio extensions
            extensions = ['.mp4', '.mkv', '.m4a', '.aac', '.mp3', '.video', '.audio']
            
            patterns = []
            for ext in extensions:
                # Check exact filename
                patterns.append(base_path + ext)
                # Check for files with copy in name
                patterns.append(base_path + '*copy*' + ext)
                # Check language-specific files
                patterns.append(base_path + '.*' + ext)
            
            existing_files = await self._find_files(patterns)

            # Delete found files
            for file in existing_files:
                try:
                    os.remove(file)
                    logger.info(f"Deleted existing file: {file}")
                except Exception as e:
                    logger.error(f"Error deleting file {file}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error checking/deleting existing files: {str(e)}")

    def _init_progress_data(self):
        """Initialize progress data structure"""
        return {
            'video': {
                'resolution': self.selected_resolution.get('resolution', 'N/A'),
                'bitrate': self.selected_resolution.get('bitrate', 0),
                'type': 'Main',
                'fragments': 0,
                'total_fragments': 0,
                'percentage': 0,
                'downloaded_size': '0MB',
                'total_size': '0MB',
                'speed': '0 KBps',
                'eta': '00:00'
            },
            'audio': {},
            'status': 'Download',
            'platform': self.content_info.get('platform', 'Unknown'),
            'filename': self.filename
        }
        
    async def _get_selected_audio_streams(self):
        """Get selected audio streams from content info."""
        return [
            stream for stream in self.content_info.get("streams_info", {}).get("audio", [])
            if stream["stream_id"] in self.selected_audios
        ]
    
    async def _get_audio_language_suffixes(self, selected_audio_streams):
        language_counts = {}
        audio_language_info = []
        
        for idx, (audio_id, audio_stream) in enumerate(zip(self.selected_audios, selected_audio_streams), 1):
            # Get language or use a default if not available
            language = audio_stream.get("language", f"audio{idx}")
            
            # Update language count and append number if needed
            if language in language_counts:
                language_counts[language] += 1
                language_suffix = f"{language}{language_counts[language]}"
            else:
                language_counts[language] = 0
                language_suffix = language
                
            audio_language_info.append((audio_id, language_suffix))
            
        return audio_language_info
        
    async def _create_final_output_file(self, video_file, audio_files):
        """Create the final output file by merging video and audio."""
        logger.info("Starting merge process...")
        # Get user_id from identifier
        user_id = self.identifier.split('_')[0] if '_' in self.identifier else None
        extension = "mp4" if user_id in MP4_USER_IDS else "mkv"
        final_file = os.path.join(self.download_dir, f"{self.filename}.{extension}")
        try:
            # If no audio files were found, just copy/rename the video file
            if not audio_files:
                logger.warning("No audio files found, copying video only")
                await self._merge_streams(video_file, [], final_file)
            else:
                # Merge with audio files
                await self._merge_streams(video_file, audio_files, final_file)
            if not os.path.exists(final_file) or os.path.getsize(final_file) == 0:
                logger.error("Merged file missing or empty")
                return None
            self.final_merged_path = final_file
            # Record stream files after muxing
            await self._record_stream_files(video_file, audio_files)
            return final_file
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return None

    async def _record_stream_files(self, video_file, audio_files):
        """Move the video/audio stream files to data/dumps/ and record their new paths in a JSON file with stream_id, content_id, and platform. Do not dump files <1MB or if needs_decryption is True and keys is empty."""
        try:
            # If DUMP_STREAMS is False, delete files and return
            if not DUMP_STREAMS:
                try:
                    if os.path.exists(video_file):
                        os.remove(video_file)
                    for audio_file in audio_files:
                        if os.path.exists(audio_file):
                            os.remove(audio_file)
                except Exception as e:
                    logger.error(f"Failed to delete files after muxing: {e}")
                return
                
            content_id = self.content_info.get("content_id") or self.content_info.get("contentId") or self.content_info.get("id")
            platform = self.content_info.get("platform")
            drm = self.content_info.get("drm", {})
            needs_decryption = drm.get("needs_decryption", False)
            keys = drm.get("keys")
            if not content_id:
                logger.warning("No content_id found in content_info, skipping stream record.")
                return
            record_path = os.path.join("data", "stream_records.json")
            dumps_dir = os.path.join("data", "dumps")
            os.makedirs(dumps_dir, exist_ok=True)
            os.makedirs("data", exist_ok=True)
            try:
                with open(record_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []
            video_stream_id = self.selected_resolution.get("stream_id")
            # Video: only dump if >=1MB and not (needs_decryption True and keys empty)
            if os.path.exists(video_file):
                skip_dump = needs_decryption and (not keys or (isinstance(keys, str) and not keys.strip()))
                if skip_dump:
                    try:
                        os.remove(video_file)
                    except Exception:
                        pass
                elif os.path.getsize(video_file) >= 1024 * 1024:
                    video_new_path = os.path.join(dumps_dir, os.path.basename(video_file))
                    if os.path.abspath(video_file) != os.path.abspath(video_new_path):
                        try:
                            shutil.move(video_file, video_new_path)
                        except Exception as e:
                            logger.error(f"Failed to move video file: {e}")
                            video_new_path = video_file
                    if video_stream_id:
                        records.append({
                            "content_id": content_id,
                            "stream_id": video_stream_id,
                            "file_path": video_new_path,
                            "type": "video",
                            "platform": platform,
                            "timestamp": time.time()  # Add timestamp
                        })
                else:
                    try:
                        os.remove(video_file)
                    except Exception:
                        pass
            selected_audio_streams = await self._get_selected_audio_streams()
            for idx, audio_file in enumerate(audio_files):
                if os.path.exists(audio_file):
                    skip_dump = needs_decryption and (not keys or (isinstance(keys, str) and not keys.strip()))
                    if skip_dump:
                        try:
                            os.remove(audio_file)
                        except Exception:
                            pass
                    elif os.path.getsize(audio_file) >= 1024 * 1024:
                        audio_new_path = os.path.join(dumps_dir, os.path.basename(audio_file))
                        if os.path.abspath(audio_file) != os.path.abspath(audio_new_path):
                            try:
                                shutil.move(audio_file, audio_new_path)
                            except Exception as e:
                                logger.error(f"Failed to move audio file: {e}")
                                audio_new_path = audio_file
                        if idx < len(self.selected_audios):
                            audio_stream_id = self.selected_audios[idx]
                            records.append({
                                "content_id": content_id,
                                "stream_id": audio_stream_id,
                                "file_path": audio_new_path,
                                "type": "audio",
                                "platform": platform,
                                "timestamp": time.time()  # Add timestamp
                            })
                    else:
                        try:
                            os.remove(audio_file)
                        except Exception:
                            pass
            with open(record_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            
            # Mark download as complete in progress JSON
            await self._update_progress_json(force=True)
                
        except Exception as e:
            logger.error(f"Failed to record stream files: {e}")

    async def execute(self):
        """Base execute method to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement this method")
    async def get_stderr(self):
        """Base get_stderr method to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement this method")

    async def _update_progress_json(self, force=False):
        """Update download progress in a structured JSON file.
        
        Structure:
        {
            "platform_name": {
                "content_id": {
                    "video_stream_id1": {
                        "percentage": 50.5,
                        "download_done": false,
                        "type": "video",
                        "resolution": "1920x1080",
                        "bitrate": 4000,
                        "speed": "1024 KBps",
                        "downloaded_size": "100MB",
                        "total_size": "200MB"
                    },
                    "video_stream_id2": {
                        "percentage": 30.5,
                        "download_done": false,
                        "type": "video",
                        "resolution": "1280x720",
                        "bitrate": 2000,
                        "speed": "512 KBps",
                        "downloaded_size": "50MB",
                        "total_size": "150MB"
                    },
                    "audio_stream_id1": {
                        "percentage": 75.2,
                        "download_done": false,
                        "type": "audio",
                        "language": "english",
                        "speed": "256 KBps",
                        "downloaded_size": "20MB",
                        "total_size": "30MB"
                    },
                    "download_complete": false
                }
            }
        }
        """
        if not self.progress_data:
            return
            
        # Only update every 10 seconds unless force=True
        current_time = time.time()
        if not force and current_time - self.last_progress_update_time < 10:
            return
            
        self.last_progress_update_time = current_time
        
        try:
            platform = self.content_info.get('platform', 'Unknown')
            content_id = self.content_info.get('content_id') or self.content_info.get('contentId') or self.content_info.get('id')
            
            if not content_id:
                logger.warning("No content_id found, skipping progress tracking")
                return
                
            progress_file = os.path.join("data", "download_progress.json")
            os.makedirs("data", exist_ok=True)
            
            # Load existing progress data
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    progress_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                progress_data = {}
                
            # Ensure nested structure exists
            if platform not in progress_data:
                progress_data[platform] = {}
            if content_id not in progress_data[platform]:
                progress_data[platform][content_id] = {"download_complete": False}
                
            # Update video progress
            video_stream_id = self.selected_resolution.get("stream_id")
            if video_stream_id:
                progress_data[platform][content_id][video_stream_id] = {
                    "percentage": self.progress_data['video'].get('percentage', 0),
                    "download_done": self.progress_data['video'].get('percentage', 0) >= 100,
                    "type": "video",
                    "resolution": self.selected_resolution.get("resolution", "N/A"),
                    "bitrate": self.selected_resolution.get("bitrate", 0),
                    "speed": self.progress_data['video'].get('speed', '0 KBps'),
                    "downloaded_size": self.progress_data['video'].get('downloaded_size', '0MB'),
                    "total_size": self.progress_data['video'].get('total_size', '0MB')
                }
                
            # Update audio progress
            for audio_idx, audio_id in enumerate(self.selected_audios):
                # Find the language for this audio stream
                language = None
                for lang, audio_data in self.progress_data.get('audio', {}).items():
                    # Just use the first language we find for this audio stream
                    language = lang
                    percentage = audio_data.get('percentage', 0)
                    progress_data[platform][content_id][audio_id] = {
                        "percentage": percentage,
                        "download_done": percentage >= 100,
                        "type": "audio",
                        "language": language,
                        "speed": audio_data.get('speed', '0 KBps'),
                        "downloaded_size": audio_data.get('downloaded_size', '0MB'),
                        "total_size": audio_data.get('total_size', '0MB')
                    }
                    break
                    
            # Check if everything is complete
            all_complete = True
            for stream_id, stream_data in progress_data[platform][content_id].items():
                if stream_id != "download_complete" and not stream_data.get("download_done", False):
                    all_complete = False
                    break
                    
            progress_data[platform][content_id]["download_complete"] = all_complete
            
            # Write progress data to file
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error updating progress JSON: {e}")

# Helper to check for dumped streams
async def get_dumped_stream_file(content_id, stream_id, stream_type, platform=None):
    # Don't use dumped files if DUMP_STREAMS is disabled
    if not DUMP_STREAMS:
        return None
        
    record_path = os.path.join("data", "stream_records.json")
    try:
        with open(record_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        for rec in records:
            fpath = rec.get("file_path", "")
            if (
                rec.get("content_id") == content_id and
                rec.get("stream_id") == stream_id and
                rec.get("type") == stream_type and
                (platform is None or rec.get("platform") == platform) and
                os.path.exists(fpath) and os.path.getsize(fpath) >= 1024 * 1024
            ):
                return fpath
    except Exception:
        pass
    return None

class YTDLPDownloader(BaseDownloader):
    def __init__(self, stream_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier):
        super().__init__(stream_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier)

    async def _build_yt_dlp_command(self, format_id, output_file):
        """Build yt-dlp command for individual stream."""
        cmd = [
            'yt-dlp',
            '-f', format_id,
            '--output', output_file,
            '--concurrent-fragments', '150',
            '--geo-bypass-country', 'IN',
            '--allow-unplayable-formats',
            '--no-part',
            '--retries', 'infinite',
            '--fragment-retries', 'infinite',
            '--file-access-retries', 'infinite',
            '--newline',
            '--progress'
        ]

        # Platform specific headers and proxy
        platform = self.content_info.get("platform")
        
        # Only add proxy if USE_PROXY is True and PROXY_URL is not None
        if USE_PROXY:
            if platform in ["JioHotstar", "ETV Win", "SunNXT", "Airtel Xstream", "SonyLIV"] and PROXY_URL:
                cmd.extend(['--proxy', PROXY_URL])
            elif platform == "ZEE5" and PROXY_URL:
                cmd.extend(['--proxy', PROXY_URL])
        if platform == "JioHotstar":
            for key, value in mpd_hotstar_headers.items():
                cmd.extend(['--add-header', f'{key}:{value}'])
        elif platform in ["Airtel Xstream"]:
            # Only use cookie from content_info
            if "cookies" in self.content_info:
                cmd.extend(['--add-header', f'Cookie: {self.content_info["cookies"]}'])
        elif platform in ["Ullu"]:
            # Only use cookie from content_info
            if "cookies" in self.content_info:
                cmd.extend(['--add-header', f'"Cookie: {self.content_info["cookies"]}"'])
                
        cmd.append(self.stream_url)
        return cmd

    async def _execute_download(self, format_id, output_file, stream_type):
        """Execute download for a single stream."""
        cmd = await self._build_yt_dlp_command(format_id, output_file)
        logger.info(f"YTDLP Download command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self.processes.append((process, stream_type, output_file))
        return process

    async def _parse_progress_line(self, line, stream_type, selected_audio_streams):
        """Parse a single line of yt-dlp output and update progress_data."""
        line = line.decode().strip()

        if self.enable_logging:  # Only log if enabled
            logger.info(f"[{stream_type}] {line}")

        # Parse video stream info
        if '[download] Destination' in line and stream_type == 'video':
            res_match = re.search(r'(\d{3,4}p)', self.progress_data['video']['resolution'])
            if res_match:
                self.progress_data['video']['resolution'] = res_match.group(1)

        if '[download]' in line:
            try:
                # Extract resolution and bitrate
                vid_info_match = re.search(r'(\d+x\d+).*?(\d+)K', line)
                if vid_info_match:
                    self.progress_data['video']['resolution'] = vid_info_match.group(1)
                    self.progress_data['video']['bitrate'] = int(vid_info_match.group(2))

                # Extract fragments
                frag_match = re.search(r'(\d+)/(\d+)\s+(\d+\.\d+)%', line)
                if frag_match:
                    self.progress_data['video']['fragments'] = int(frag_match.group(1))
                    self.progress_data['video']['total_fragments'] = int(frag_match.group(2))
                    self.progress_data['video']['percentage'] = float(frag_match.group(3))

                # Extract size info
                size_match = re.search(r'([\d.]+)MiB/([\d.]+)MiB', line)
                if size_match:
                    self.progress_data['video']['downloaded_size'] = f"{size_match.group(1)}MB"
                    self.progress_data['video']['total_size'] = f"{size_match.group(2)}MB"

                # Extract speed and ETA
                speed_match = re.search(r'(\d+\.?\d*[KM]iB/s)', line)
                eta_match = re.search(r'ETA (\d+:\d+)', line)

                if speed_match:
                    speed = speed_match.group(1)
                    if 'MiB/s' in speed:
                        mb = float(speed.replace('MiB/s', '')) * 1024
                        self.progress_data['video']['speed'] = f"{mb:.0f} KBps"
                    else:
                        self.progress_data['video']['speed'] = f"{speed.replace('KiB/s', '')} KBps"

                if eta_match:
                    self.progress_data['video']['eta'] = eta_match.group(1)

                if stream_type == 'video' and not frag_match:
                    general_percent = re.search(r'(\d+\.\d+)%', line)
                    if general_percent:
                        self.progress_data['video']['percentage'] = float(general_percent.group(1))

                if stream_type.startswith('audio_'):
                    audio_idx = int(stream_type.split('_')[1]) - 1
                    if 0 <= audio_idx < len(selected_audio_streams):
                        language = selected_audio_streams[audio_idx]["language"]
                        if language not in self.progress_data['audio']:
                            self.progress_data['audio'][language] = {
                                'percentage': 0,
                                'speed': '0 KBps',
                                'downloaded_size': '0MB',
                                'total_size': '0MB'
                            }
                        audio_percent = re.search(r'(\d+\.\d+)%', line)
                        if audio_percent:
                            current = float(audio_percent.group(1))
                            self.progress_data['audio'][language]['percentage'] = 100 if current >= 94 else current

                download_progress.update_progress(self.identifier, self.progress_data)
                await self._update_progress_json()

            except Exception as e:
                logger.error(f"Progress parsing error: {e}")

    async def _monitor_progress(self, process, stream_type, output_file):
        """Monitor download progress for a single stream."""
        # Initialize progress data
        if self.progress_data is None:
            self.progress_data = self._init_progress_data()

        selected_audio_streams = await self._get_selected_audio_streams()

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            await self._parse_progress_line(line, stream_type, selected_audio_streams)

        return await process.wait()

    async def get_stderr(self):
        """Get stderr from all processes."""
        stderr_data = []
        for process, stream_type, _ in self.processes:
            if process.stderr:
                stderr = await process.stderr.read()
                if stderr:
                    stderr_data.append(f"{stream_type}: {stderr.decode()}")
        return "\n".join(stderr_data).encode() if stderr_data else None

    async def _decrypt_file(self, file_path, keys_dict):
        """Attempt to decrypt a single file using all available keys."""
        output_path = file_path + '.decrypted'
        
        cmd = ['mp4decrypt']
        for kid, key in keys_dict.items():
            cmd.extend(['--key', f'{kid}:{key}'])
        cmd.extend([file_path, output_path])
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        if process.returncode == 0:
            os.replace(output_path, file_path)
            return True
        else:
            if os.path.exists(output_path):
                os.remove(output_path)
            return False

    async def _decrypt_streams(self, files_to_decrypt):
        """Decrypt downloaded streams if necessary."""
        if not self.content_info or 'drm' not in self.content_info or not self.content_info['drm'].get('keys'):
            return files_to_decrypt

        keys_str = self.content_info['drm']['keys']
        key_pairs = keys_str.split(',') if isinstance(keys_str, str) else keys_str
        keys_dict = {kid.strip(): key.strip() for pair in key_pairs for kid, key in [pair.split(':')]}

        decrypted_files = []
        
        try:
            # Try mp4decrypt first
            for file_path in files_to_decrypt:
                success = await self._decrypt_file(file_path, keys_dict)
                if not success:
                    # Fall back to Shaka Packager if mp4decrypt fails
                    success = await self._decrypt_file_shaka(file_path, keys_dict)
                    if not success:
                        raise Exception(f"Failed to decrypt {file_path}")
                decrypted_files.append(file_path)
            
            return decrypted_files
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise

    async def _download_and_monitor(self):
        """Downloads video and audio streams and monitors their progress, using dumps if available."""
        selected_audio_streams = await self._get_selected_audio_streams()
        content_id = self.content_info.get("content_id") or self.content_info.get("contentId") or self.content_info.get("id")

        # Video
        video_stream_id = self.selected_resolution["stream_id"]
        video_file = await get_dumped_stream_file(content_id, video_stream_id, "video", self.content_info.get("platform"))
        if video_file:
            logger.info(f"Using dumped video file: {video_file}")
            # Set video progress to 100%
            if self.progress_data is None:
                self.progress_data = self._init_progress_data()
            self.progress_data['video']['percentage'] = 100
            self.progress_data['video']['downloaded_size'] = self.progress_data['video']['total_size'] = f"{os.path.getsize(video_file) // (1024*1024)}MB"
            download_progress.update_progress(self.identifier, self.progress_data)
        else:
            video_file = os.path.join(self.download_dir, f"{self.filename}.video")
            await self._execute_download(video_stream_id, video_file, 'video')

        # Audio
        audio_language_info = await self._get_audio_language_suffixes(selected_audio_streams)
        audio_files = []
        for idx, (audio_id, language_suffix) in enumerate(audio_language_info, 1):
            audio_file = await get_dumped_stream_file(content_id, audio_id, "audio", self.content_info.get("platform"))
            if audio_file:
                logger.info(f"Using dumped audio file: {audio_file}")
                # Set audio progress to 100%
                if self.progress_data is None:
                    self.progress_data = self._init_progress_data()
                lang = selected_audio_streams[idx-1]["language"] if idx-1 < len(selected_audio_streams) else language_suffix
                if lang not in self.progress_data['audio']:
                    self.progress_data['audio'][lang] = {}
                self.progress_data['audio'][lang]['percentage'] = 100
                self.progress_data['audio'][lang]['downloaded_size'] = self.progress_data['audio'][lang]['total_size'] = f"{os.path.getsize(audio_file) // (1024*1024)}MB"
                download_progress.update_progress(self.identifier, self.progress_data)
            else:
                audio_file = os.path.join(self.download_dir, f"{self.filename}.{language_suffix}")
                await self._execute_download(audio_id, audio_file, f'audio_{idx}')
            audio_files.append(audio_file)

        # Only monitor downloads that were actually started
        tasks = [self._monitor_progress(process, stream_type, output_file) for process, stream_type, output_file in self.processes]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return video_file, audio_files

    async def _check_downloaded_files(self, video_file, audio_files):
        """Checks if downloaded files exist and are not empty."""
        if not os.path.exists(video_file) or os.path.getsize(video_file) == 0:
            logger.error(f"Video file missing or empty: {video_file}")
            return False

        for audio_file in audio_files:
            if not os.path.exists(audio_file) or os.path.getsize(audio_file) == 0:
                logger.error(f"Audio file missing or empty: {audio_file}")
                return False
        return True

    async def execute(self):
        """Execute the download, decryption, and merge process."""
        try:
            # Check and delete existing files first
            await self._check_and_delete_existing_files()
            
            video_file, audio_files = await self._download_and_monitor()

            if not await self._check_downloaded_files(video_file, audio_files):
                return 1

            if self.needs_decryption:
                files_to_decrypt = [video_file] + audio_files
                try:
                    await self._decrypt_streams(files_to_decrypt)
                except Exception as e:
                    logger.error(f"Decryption failed: {e}")
                    return 1

            final_file = await self._create_final_output_file(video_file, audio_files)
            
            if not final_file:
                return 1
                
            # Update progress JSON with download complete
            if self.progress_data is None:
                self.progress_data = self._init_progress_data()
            self.progress_data['video']['percentage'] = 100
            for lang in self.progress_data.get('audio', {}):
                self.progress_data['audio'][lang]['percentage'] = 100
            download_progress.update_progress(self.identifier, self.progress_data)
            await self._update_progress_json(force=True)
            
            return 0

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return 1
        
    async def _decrypt_file_shaka(self, file_path, keys_dict):
        """Attempt to decrypt a single file using Shaka Packager."""
        output_path = file_path + '.decrypted'
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            packager_path = os.path.join(script_dir, 'packager')
            
            if not os.path.exists(packager_path):
                return False
            
            if not os.access(packager_path, os.X_OK):
                os.chmod(packager_path, 0o755)
            
            cmd = [packager_path, '--enable_raw_key_decryption']
            
            is_video = not any(audio_indicator in file_path.lower() 
                             for audio_indicator in ['.aac', '.mp3', '.m4a', '.audio', '.hindi', '.tamil', '.telugu'])
            drm_label = "VIDEO" if is_video else "AUDIO"
            
            key_specs = []
            for idx, (kid, key) in enumerate(keys_dict.items(), 1):
                label = f"{drm_label}{idx if idx > 1 else ''}"
                key_specs.append(f"label={label}:key_id={kid}:key={key}")
            if key_specs:
                cmd.extend(['--keys', ','.join(key_specs)])
            
            input_format = "webm" if file_path.lower().endswith('.webm') else "mp4"
            output_format = input_format
            
            stream_descriptor = (
                f"input={file_path},"
                f"stream_selector=0,"
                f"drm_label={drm_label},"
                f"output={output_path},"
                f"input_format={input_format},"
                f"output_format={output_format}"
            )
            
            cmd.append(stream_descriptor)
            
            logger.info("Running Shaka Packager command:")
            logger.info(f"Command: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            await process.communicate()
            
            if process.returncode == 0:
                os.replace(output_path, file_path)
                return True
            else:
                if os.path.exists(output_path):
                    os.remove(output_path)
                return False
                
        except FileNotFoundError:
            return False
        except Exception:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass
            return False

class Nm3u8DLREDownloader(BaseDownloader):
    def __init__(self, stream_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier):
        super().__init__(stream_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier)

    async def _build_common_command_parts(self, stream_type, stream_id=None, language_suffix=None):
        """Build common parts of N_m3u8DL-RE command"""
        platform = self.content_info.get("platform")
        
        # Base command with stream URL
        cmd_parts = [f"N_m3u8DL-RE '{self.stream_url}'"]
        
        # Check if user wants MP4 format
        user_id = self.identifier.split('_')[0] if '_' in self.identifier else None
        use_mp4 = user_id in MP4_USER_IDS
        
        # Stream selection based on type
        if stream_type == "video":
            # Video stream selection
            if platform == "DisneyPlus":
                bitrate = self.selected_resolution.get("bitrate", 1000)
                video_param = f'-sv "res={self.selected_resolution["resolution"]}:bwMax={bitrate}"'
            elif platform in ["Tata Play Binge", "ETV Win"]:
                video_param = f'-sv "res={self.selected_resolution["resolution"]}"'
            else:
                resolution_part = ""
                if self.selected_resolution["resolution"] != "3840x2160":
                    resolution_part = f"|res={self.selected_resolution['resolution']}"
                
                # Handle MXPlayer stream IDs
                stream_id = self.selected_resolution["stream_id"]
                if platform == "MXPlayer" and "-" in stream_id:
                    stream_id = stream_id.split("-")[0]
                
                # Always include resolution parameter
                video_param = f'-sv "id={stream_id}|res={self.selected_resolution["resolution"]}:for=worst"'
            
            cmd_parts.append(video_param)
            
            # Include subtitle selection for video streams
            if platform == "Amazon Prime":
                subtitle_param = ''
            else:
                subtitle_param = '-ss "all"'
            cmd_parts.append(subtitle_param)
            
            cmd_parts.append('-da "all"')
            
            # Add concurrent download flag
            cmd_parts.append('-mt')
            
            # Add mux-after-done option with proper format
            mux_format = "mp4" if use_mp4 else "mkv"
            cmd_parts.append(f'-M "format={mux_format}"')
            
            save_name = f"{self.filename}.video"
            
        elif stream_type == "audio":
            # Audio stream selection
            if platform == "ETV Win":
                audio_param = '-sa "best"'
            elif platform == "DisneyPlus":
                audio_param = '-sa "lang=en:for=best3"'
            elif stream_id:
                # Use only the specific audio ID for this command, not all selected audios
                if platform == "MXPlayer" and "-" in stream_id:
                    stream_id = stream_id.split("-")[0]
                audio_param = f'-sa "id={stream_id}:for=best"'
            else:
                # Fallback, though this shouldn't happen normally
                audio_param = '-sa "best"'
            cmd_parts.append(audio_param)
            cmd_parts.extend(['-dv "all"', '-ds "all"'])
            save_name = f"{self.filename}.{language_suffix}"
        
        # Output parameters
        cmd_parts.extend([
            '--thread-count 40',
            '--skip-merge false',
            '--del-after-done false',
            '--write-meta-json false',
            f'--save-dir "{self.download_dir}"',
            f'--save-name "{save_name}"'
        ])
        # Add proxy if needed
        if USE_PROXY:
            if platform == "ZEE5" and PROXY_URL:
                cmd_parts.append(f'--custom-proxy "{PROXY_URL}"')
            elif platform in ["ETV Win", "JioHotstar", "SunNXT", "Airtel Xstream", "SonyLIV"] and PROXY_URL:
                cmd_parts.append(f'--custom-proxy "{PROXY_URL}"')
        
        # Add platform-specific headers
        if platform == "SonyLIV":
            for key, value in sonyliv_mpd_headers.items():
                escaped_value = value.replace('"', '\\"')
                cmd_parts.append(f'-H "{key}: {escaped_value}"')
        elif platform == "JioHotstar":
            for key, value in mpd_hotstar_headers.items():
                cmd_parts.append(f'-H "{key}: {value}"')
        elif platform == "Airtel Xstream":
            # Only use cookie from content_info
            if "cookies" in self.content_info:
                cmd_parts.append(f'-H "Cookie: {self.content_info["cookies"]}"')
        # SAINAPLAY INTEGRATION START
        elif platform == "SainaPlay":
            # The handle_sainaplay function MUST add the session token to content_info
            session_token = self.content_info.get("session")
            if session_token:
                cmd_parts.append(f'-H "x-session: {session_token}"')
            # Add other static headers for SainaPlay
            cmd_parts.append('-H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Joker/537.36"')
            cmd_parts.append('-H "Referer: https://sainaplay.com/"')
            cmd_parts.append('-H "Origin: https://sainaplay.com/"')
        # SAINAPLAY INTEGRATION END
        # STREAMNXT INTEGRATION START
        elif platform == "Stream NXT":
            # StreamNXT MPD URLs are CDN links that do not require special headers for download.
            # The x-session token is used for API calls, not for the final stream download.
            # Using a generic user-agent.
            cmd_parts.append('-H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"')
        # STREAMNXT INTEGRATION END
            
        # Add DRM keys if needed
        if self.content_info.get("drm", {}).get("needs_decryption") and self.content_info.get("drm", {}).get("keys"):
            keys = self.content_info["drm"]["keys"]
            key_pairs = keys.split(",") if isinstance(keys, str) else keys
            cmd_parts.extend('--key "{}"'.format(key.strip()) for key in key_pairs)
            
        return cmd_parts

    async def build_video_command(self):
        """Build the N_m3u8DL-RE command for video download"""
        cmd_parts = await self._build_common_command_parts("video")
        return " ".join(cmd_parts)
        
    async def build_audio_command(self, audio_id, language_suffix):
        """Build the N_m3u8DL-RE command for audio download"""
        cmd_parts = await self._build_common_command_parts("audio", audio_id, language_suffix)
        return " ".join(cmd_parts)
    
    async def _execute_download(self, cmd, stream_type):
        """Execute download for a single stream."""
        logger.info(f"[{stream_type}] Download command: {cmd}")

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        self.processes.append((process, stream_type))
        return process

    async def _monitor_progress(self, process, stream_type):
        """Monitor download progress for a single stream."""
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            line = line.decode().strip()
            if line:
                if self.enable_logging:  # Only log if enabled
                    logger.info(f"[{stream_type}] {line}")
                try:
                    if self.progress_data:
                        self.progress_data = await progress_display.update_progress_from_line(
                            line, self.progress_data, self.identifier
                        )
                        download_progress.update_progress(self.identifier, self.progress_data)
                        await self._update_progress_json()
                except Exception as e:
                    logger.error(f"Error updating progress for {self.identifier}: {e}")

        return await process.wait()

    async def get_stderr(self):
        """Get any remaining stderr output from all processes"""
        stderr_data = []
        for process, stream_type in self.processes:
            if process.stderr:
                stderr = await process.stderr.read()
                if stderr:
                    stderr_data.append(f"{stream_type}: {stderr.decode()}")
        return "\n".join(stderr_data).encode() if stderr_data else None

    async def execute(self):
        """Execute the download process and monitor progress, using dumps if available."""
        try:
            await self._check_and_delete_existing_files()
            self.progress_data = self._init_progress_data()
            download_progress.update_progress(self.identifier, self.progress_data)
            
            selected_audio_streams = await self._get_selected_audio_streams()
            audio_language_info = await self._get_audio_language_suffixes(selected_audio_streams)
            audio_track_info = []
            content_id = self.content_info.get("content_id") or self.content_info.get("contentId") or self.content_info.get("id")

            # Video
            video_stream_id = self.selected_resolution["stream_id"]
            video_file = await get_dumped_stream_file(content_id, video_stream_id, "video", self.content_info.get("platform"))
            if video_file:
                logger.info(f"Using dumped video file: {video_file}")
                # Set video progress to 100%
                self.progress_data['video']['percentage'] = 100
                self.progress_data['video']['downloaded_size'] = self.progress_data['video']['total_size'] = f"{os.path.getsize(video_file) // (1024*1024)}MB"
                download_progress.update_progress(self.identifier, self.progress_data)
            else:
                video_cmd = await self.build_video_command()
                video_file = os.path.join(self.download_dir, f"{self.filename}.video")
                video_process = await self._execute_download(video_cmd, 'video')

            # Audio
            audio_files = []
            for idx, (audio_id, language_suffix) in enumerate(audio_language_info, 1):
                audio_file = await get_dumped_stream_file(content_id, audio_id, "audio", self.content_info.get("platform"))
                if audio_file:
                    logger.info(f"Using dumped audio file: {audio_file}")
                    # Set audio progress to 100%
                    lang = selected_audio_streams[idx-1]["language"] if idx-1 < len(selected_audio_streams) else language_suffix
                    if lang not in self.progress_data['audio']:
                        self.progress_data['audio'][lang] = {}
                    self.progress_data['audio'][lang]['percentage'] = 100
                    self.progress_data['audio'][lang]['downloaded_size'] = self.progress_data['audio'][lang]['total_size'] = f"{os.path.getsize(audio_file) // (1024*1024)}MB"
                    download_progress.update_progress(self.identifier, self.progress_data)
                else:
                    audio_cmd = await self.build_audio_command(audio_id, language_suffix)
                    audio_file = os.path.join(self.download_dir, f"{self.filename}.{language_suffix}")
                    await self._execute_download(audio_cmd, f'audio_{idx}')
                audio_files.append(audio_file)
                audio_track_info.append((language_suffix, audio_id))

            # Only monitor downloads that were actually started
            monitoring_tasks = [self._monitor_progress(process, stream_type) for process, stream_type in self.processes]
            if monitoring_tasks:
                await asyncio.gather(*monitoring_tasks)

            # Find the video file (if it was downloaded, it will be in the download dir, else it's from dump)
            if not os.path.exists(video_file):
                # Try to find it by pattern (for downloaded case)
                video_patterns = [
                    os.path.join(self.download_dir, f"{self.filename}.video.*"),
                    os.path.join(self.download_dir, f"{self.filename}.*.[mw][kp][v4]")
                ]
                res = self.selected_resolution.get("resolution", "")
                if res:
                    res_pattern = res.split("x")[1] + "p" if "x" in res else res
                    video_patterns.append(os.path.join(self.download_dir, f"*{res_pattern}*.[mw][kp][v4]"))
                video_files = await self._find_files(video_patterns)
                if video_files:
                    video_files.sort(key=lambda x: os.path.getsize(x), reverse=True)
                    video_file = video_files[0]
                    logger.info(f"Found video file: {video_file}")
                else:
                    logger.error("No video file found in download directory")
                    return 1

            # Find audio files (if not from dump)
            final_audio_files = []
            for idx, (language_suffix, audio_id) in enumerate(audio_track_info):
                audio_file = audio_files[idx]
                if not os.path.exists(audio_file):
                    # Try to find it by pattern
                    audio_patterns = [
                        os.path.join(self.download_dir, f"{self.filename}.{language_suffix}.*"),
                        os.path.join(self.download_dir, f"*part{language_suffix}*.*"),
                        os.path.join(self.download_dir, f"*{language_suffix}*.m4a"),
                        os.path.join(self.download_dir, f"*{language_suffix}*.aac"),
                        os.path.join(self.download_dir, f"*{audio_id}*.*")
                    ]
                    found_audio_files = await self._find_files(audio_patterns)
                    audio_matches = [f for f in found_audio_files if not f.endswith(('.mp4', '.mkv', '.webm', '.srt', '.vtt'))]
                    if audio_matches:
                        audio_file = audio_matches[0]
                        logger.info(f"Found audio file for {language_suffix}: {audio_file}")
                final_audio_files.append(audio_file)

            # Deduplicate audio files while preserving order
            seen_files = set()
            ordered_audio_files = []
            for file in final_audio_files:
                if file not in seen_files:
                    seen_files.add(file)
                    ordered_audio_files.append(file)

            logger.info(f"Video file for merging: {video_file}")
            logger.info(f"Audio files for merging (in order): {ordered_audio_files}")

            final_file = await self._create_final_output_file(video_file, ordered_audio_files)
            if not final_file:
                return 1
                
            # Update progress JSON with download complete
            self.progress_data['video']['percentage'] = 100
            for lang in self.progress_data.get('audio', {}):
                self.progress_data['audio'][lang]['percentage'] = 100
            download_progress.update_progress(self.identifier, self.progress_data)
            await self._update_progress_json(force=True)
            
            await self._record_stream_files(video_file, ordered_audio_files)
            return 0
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return 1

    async def get_stderr(self):
        """Get stderr from all processes."""
        stderr_data = []
        for process, stream_type in self.processes:
            if process.stderr:
                stderr = await process.stderr.read()
                if stderr:
                    stderr_data.append(f"{stream_type}: {stderr.decode()}")
        return "\n".join(stderr_data).encode() if stderr_data else None

class QBitDownloader(BaseDownloader):
    """QBitDownloader class for handling TMDB magnet links using qBittorrent Web API."""
    def __init__(self, magnet_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier, file_idx=None):
        super().__init__(stream_url=magnet_url, selected_resolution=selected_resolution, selected_audios=selected_audios, 
                        content_info=content_info, download_dir=download_dir, filename=filename, identifier=identifier)
        self.magnet_url = magnet_url
        self.file_idx = file_idx
        self.final_merged_path = None
        
        # qBittorrent settings
        self.qb_port = self._get_available_port()
        self.qb_host = f"http://localhost:{self.qb_port}/"
        self.qb_username = "admin"
        self.qb_password = "adminadmin"
        self.root_download_path = "/root/Downloads"
        self.config_dir = f"/tmp/qbittorrent_config_{self.qb_port}"
        self.qb_process = None
        
        logger.info(f"QBitDownloader initialized with WebUI at {self.qb_host} using config dir {self.config_dir}")
        
    def _get_available_port(self, start=8775, end=8795):
        """Find an available port in the given range."""
        import socket
        for port in range(start, end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('localhost', port)) != 0:
                    return port
        return start
        
    async def _check_qbittorrent_running(self):
        """Check if qBittorrent is already running on our port."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(self.qb_host, timeout=2) as response:
                    return response.status == 200
        except:
            return False
            
    async def _start_qbittorrent(self):
        """Start qBittorrent-nox instance."""
        if await self._check_qbittorrent_running():
            logger.info(f"qBittorrent is already running on port {self.qb_port}")
            return True
            
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            cmd = ['qbittorrent-nox', f'--webui-port={self.qb_port}', f'--configuration={self.config_dir}']
            
            self.qb_process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.sleep(2)
            logger.info(f"Started qBittorrent-nox on port {self.qb_port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start qBittorrent-nox: {e}")
            return False
    
    async def _stop_qbittorrent(self):
        """Stop the qBittorrent instance."""
        if not self.qb_process:
            return False
            
        try:
            self.qb_process.terminate()
            try:
                await asyncio.wait_for(self.qb_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.qb_process.kill()
                await self.qb_process.wait()
            
            logger.info(f"Stopped qBittorrent instance on port {self.qb_port}")
            return True
        except Exception as e:
            logger.error(f"Error stopping qBittorrent: {e}")
            return False

    async def _init_qbittorrent_client(self):
        """Initialize qBittorrent client with automatic port selection."""        
        for _ in range(20):  # Try up to 20 different ports
            if _ > 0:
                self.qb_port = self._get_available_port(self.qb_port + 1, 8795)
                self.qb_host = f"http://localhost:{self.qb_port}/"
                self.config_dir = f"/tmp/qbittorrent_config_{self.qb_port}"
                logger.info(f"Trying port: {self.qb_port}")
            
            if not await self._start_qbittorrent():
                continue
                
            try:
                qb = Client(self.qb_host)
                qb.login(self.qb_username, self.qb_password)
                logger.info(f"Connected to qBittorrent WebUI on port {self.qb_port}")
                return qb
            except Exception as e:
                logger.warning(f"Connection failed on port {self.qb_port}: {e}")
                await self._stop_qbittorrent()
        
        logger.error("Failed to connect to qBittorrent after trying multiple ports")
        return None
            
    async def _extract_torrent_hash(self):
        """Extract hash from magnet link."""
        try:
            return self.magnet_url.split('btih:')[1].split('&')[0].lower()
        except Exception as e:
            logger.error(f"Failed to extract torrent hash: {e}")
            return None
            
    async def _wait_for_metadata(self, qb, torrent_hash, timeout=180):
        """Wait for torrent metadata with progress updates."""
        logger.info("Waiting for torrent metadata...")
        
        for i in range(timeout):
            try:
                for t in qb.torrents():
                    if t.get('hash', '').lower() == torrent_hash:
                        files = qb.get_torrent_files(torrent_hash)
                        if files:
                            logger.info(f"Got metadata after {i} seconds")
                            return files
            except Exception as e:
                logger.warning(f"Error checking metadata: {e}")
                
            if i % 5 == 0:
                self.progress_data['video']['percentage'] = min(5 + i/5, 15)
                download_progress.update_progress(self.identifier, self.progress_data)
                
            await asyncio.sleep(1)
        
        logger.error("Failed to get torrent metadata after 3 minutes")
        return None
        
    async def _select_file(self, files):
        """Select file to download based on size or index."""
        if self.file_idx is None:
            # Auto-select largest video file
            video_files = [(i, f) for i, f in enumerate(files) 
                          if any(f.get('name', '').lower().endswith(ext) 
                          for ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm'])]
            if video_files:
                self.file_idx = max(video_files, key=lambda x: x[1].get('size', 0))[0]
                logger.info(f"Auto-selected file index {self.file_idx}")
            else:
                logger.error("No video files found")
                return None
        elif self.file_idx >= len(files):
            logger.error(f"File index {self.file_idx} out of range")
            return None
        
        selected_file = files[self.file_idx]
        logger.info(f"Selected file: {selected_file.get('name')} (idx: {self.file_idx})")
        return selected_file
            
    async def _download_and_monitor(self, qb, torrent_hash):
        """Monitor download progress with error detection."""
        logger.info("Starting download and monitoring progress...")
        last_progress = -1
        last_update = time.time()
        issue_times = {'slow': None, 'stalled': None}
        last_progress_value = 0
        
        while True:
            await asyncio.sleep(1)
            if time.time() - last_update < 1:
                continue
                
            last_update = time.time()
            
            try:
                for t in qb.torrents():
                    if t.get('hash', '').lower() == torrent_hash:
                        progress = t.get('progress', 0) * 100
                        speed = t.get('dlspeed', 0)
                        state = t.get('state', '')
                        size = t.get('size', 0)
                        
                        # Check for issues
                        slow = speed < 200 * 1024 and state not in ['pausedUP', 'uploading', 'stalledUP']
                        stalled = abs(progress - last_progress_value) < 0.1
                        
                        for issue, condition in [('slow', slow), ('stalled', stalled)]:
                            if condition:
                                if not issue_times[issue]:
                                    issue_times[issue] = time.time()
                                elif time.time() - issue_times[issue] > 3600:
                                    logger.error(f"Download {issue} for over an hour")
                                    return False
                            else:
                                issue_times[issue] = None
                        
                        if not stalled:
                            last_progress_value = progress
                            
                        # Update progress
                        if abs(progress - last_progress) >= 0.5 or time.time() - last_update > 5:
                            last_progress = progress
                            self.progress_data['video'].update({
                                'percentage': 15 + (progress * 0.85),
                                'speed': f"{speed / 1024:.0f} KBps",
                                'downloaded_size': f"{(size * progress / 100) / (1024 * 1024):.2f}MB",
                                'total_size': f"{size / (1024 * 1024):.2f}MB"
                            })
                            download_progress.update_progress(self.identifier, self.progress_data)
                            await self._update_progress_json()
                            logger.info(f"Progress: {progress:.1f}% | Speed: {speed/1024:.1f} KB/s | State: {state}")
                            
                        if progress >= 99.9 or state in ['pausedUP', 'uploading', 'stalledUP']:
                            logger.info("Download complete!")
                            self.progress_data['video']['percentage'] = 100
                            download_progress.update_progress(self.identifier, self.progress_data)
                            await self._update_progress_json(force=True)
                            return True
                            
                        break
                else:
                    logger.error("Torrent not found")
                    return False
                    
            except Exception as e:
                logger.error(f"Error monitoring download: {e}")
                await asyncio.sleep(5)
                
        return False
    
    async def _process_downloaded_file(self, qb, torrent_hash, selected_file):
        """Copy downloaded file to final location."""
        src_path = os.path.join(self.root_download_path, self.download_dir, selected_file.get('name', ''))
        self.final_merged_path = os.path.join(self.download_dir, f"{self.filename}{os.path.splitext(src_path)[1]}")
        
        os.makedirs(os.path.dirname(self.final_merged_path), exist_ok=True)
        
        if os.path.exists(src_path):
            try:
                with open(src_path, 'rb') as src, open(self.final_merged_path, 'wb') as dst:
                    while chunk := src.read(10 * 1024 * 1024):
                        dst.write(chunk)
                logger.info(f"File copied to: {self.final_merged_path}")
                return True
            except Exception as e:
                logger.error(f"Error copying file: {e}")
        else:
            logger.error(f"Downloaded file not found: {src_path}")
        return False
    
    async def _cleanup_resources(self, qb, torrent_hash):
        """Clean up all resources."""
        try:
            qb.delete_permanently(torrent_hash)
            logger.info(f"Deleted torrent {torrent_hash}")
        except Exception as e:
            logger.warning(f"Error deleting torrent: {e}")
        
        await self._stop_qbittorrent()
        
        try:
            import shutil
            if os.path.exists(self.config_dir):
                shutil.rmtree(self.config_dir)
                logger.info(f"Removed config directory: {self.config_dir}")
        except Exception as e:
            logger.warning(f"Error removing config directory: {e}")
            
    async def execute(self):
        """Execute torrent download process."""
        qb = None
        torrent_hash = None
        
        try:
            await self._check_and_delete_existing_files()
            self.progress_data = self._init_progress_data()
            download_progress.update_progress(self.identifier, self.progress_data)
            
            qb = await self._init_qbittorrent_client()
            if not qb:
                return 1
                
            torrent_hash = await self._extract_torrent_hash()
            if not torrent_hash:
                return 1
            
            os.makedirs(self.download_dir, exist_ok=True)
            qb.download_from_link(self.magnet_url, savepath=self.download_dir)
            
            files = await self._wait_for_metadata(qb, torrent_hash)
            if not files:
                return 1
                
            selected_file = await self._select_file(files)
            if not selected_file:
                return 1
            
            # Configure download
            qb.pause(torrent_hash)
            for i in range(len(files)):
                qb.set_file_priority(torrent_hash, i, 1 if i == self.file_idx else 0)
            qb.set_torrent_upload_limit(torrent_hash, 0)
            qb.resume(torrent_hash)
            
            if not await self._download_and_monitor(qb, torrent_hash):
                return 1
            
            qb.pause(torrent_hash)
            if not await self._process_downloaded_file(qb, torrent_hash, selected_file):
                return 1
                
            return 0

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return 1
        finally:
            if qb and torrent_hash:
                await self._cleanup_resources(qb, torrent_hash)
            elif self.qb_process:
                await self._stop_qbittorrent()
        
    async def get_stderr(self):
        """Get stderr from processes."""
        return f"QBitDownloader error: {getattr(self, 'last_error', '')}".encode() if hasattr(self, 'last_error') and self.last_error else None

class TataPlayMultiPartDownloader(BaseDownloader):
    """Downloader for Tata Play content with multiple MPD parts"""
    def __init__(self, stream_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier):
        super().__init__(stream_url, selected_resolution, selected_audios, content_info, download_dir, filename, identifier)
        self.parts = content_info.get("streams", {}).get("parts", {})
        self.total_parts = len(self.parts)
        self.current_part = 0

    async def _build_common_command_parts(self, stream_type, part_index, part_info, audio_id=None, language_suffix=None):
        """Build common command parts for a specific part"""
        stream_url, key = part_info.get("path"), part_info.get("key")
        
        cmd_parts = [
            f'N_m3u8DL-RE "{stream_url}"',
            '-H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.69.69.69 XtRoN/537.36"',
            '-H "Referer: https://watch.tataplay.com/"',
            '-H "Origin: https://watch.tataplay.com/"',
            '-mt',
            '--thread-count 40',
            '--skip-merge false',
            '--del-after-done false',
            '--live-perform-as-vod',
            '--write-meta-json false',
            f'--save-dir "{self.download_dir}"'
        ]

        if USE_PROXY and PROXY_URL:
            cmd_parts.append(f'--custom-proxy "{PROXY_URL}"')
            
        if key:
            cmd_parts.append(f'--key "{key}"')

        save_name = f"{self.filename}.part{part_index}"
        if stream_type == "video":
            cmd_parts.extend([
                f'-sv "id={self.selected_resolution["stream_id"]}:for=worst"',
                '-ss "all"',
                '-da "all"'
            ])
            save_name += ".video"
        else:
            cmd_parts.extend([
                f'-sa "id={audio_id}:for=best"',
                '-dv "all"',
                '-ds "all"'
            ])
            save_name += f".{language_suffix}"

        cmd_parts.append(f'--save-name "{save_name}"')
        return cmd_parts

    async def _build_video_command(self, part_index, part_info):
        """Build command for downloading video of a specific part"""
        return " ".join(await self._build_common_command_parts("video", part_index, part_info))

    async def _build_audio_command(self, part_index, part_info, audio_id, language_suffix):
        """Build command for downloading an audio stream of a specific part"""
        return " ".join(await self._build_common_command_parts("audio", part_index, part_info, audio_id, language_suffix))

    async def _execute_download(self, cmd, stream_type):
        """Execute download for a single stream"""
        logger.info(f"[{stream_type}] Download command: {cmd}")
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, shell=True
        )
        self.processes.append((process, stream_type))
        return process

    async def _monitor_progress(self, process, stream_type, part_index):
        """Monitor download progress with overall progress tracking"""
        part_idx = int(part_index)
        part_weight = 100.0 / self.total_parts
        is_zero_indexed = '0' in self.parts or 0 in self.parts
        part_base = (part_idx if is_zero_indexed else part_idx - 1) * part_weight
        max_part_percentage = 0

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line = line.decode().strip()
            if not line:
                continue

            logger.info(f"[{stream_type}] {line}")
            try:
                if self.progress_data:
                    part_progress = await progress_display.update_progress_from_line(
                        line, self.progress_data.copy(), self.identifier
                    )
                    
                    part_percentage = part_progress['video']['percentage']
                    max_part_percentage = max(max_part_percentage, part_percentage)
                    overall_percentage = part_base + (max_part_percentage * part_weight / 100)
                    
                    self.progress_data = part_progress
                    self.progress_data['video']['percentage'] = overall_percentage
                    
                    for audio_lang in self.progress_data.get('audio', {}):
                        audio_part_percentage = self.progress_data['audio'][audio_lang].get('percentage', 0)
                        self.progress_data['audio'][audio_lang]['percentage'] = part_base + (audio_part_percentage * part_weight / 100)
                    
                    download_progress.update_progress(self.identifier, self.progress_data)
                    await self._update_progress_json()
            except Exception as e:
                logger.error(f"Error updating progress for {self.identifier}: {e}")

        if self.progress_data:
            final_percentage = part_base + part_weight
            self.progress_data['video']['percentage'] = final_percentage
            for audio_lang in self.progress_data.get('audio', {}):
                self.progress_data['audio'][audio_lang]['percentage'] = final_percentage
            download_progress.update_progress(self.identifier, self.progress_data)
            await self._update_progress_json()

        return await process.wait()

    async def _find_files_with_patterns(self, patterns, exclude_extensions=None):
        """Generic file finder with pattern matching and exclusions"""
        files = await self._find_files(patterns)
        if exclude_extensions:
            files = [f for f in files if not f.endswith(tuple(exclude_extensions))]
        if files:
            files.sort(key=lambda x: os.path.getsize(x), reverse=True)
            return files[0]
        return None

    async def _find_video_file(self, part_index):
        """Find the video file for a specific part"""
        patterns = [
            os.path.join(self.download_dir, f"{self.filename}.part{part_index}.video.*"),
            os.path.join(self.download_dir, f"*part{part_index}*video*")
        ]
        
        res = self.selected_resolution.get("resolution", "")
        if res:
            res_pattern = res.split("x")[1] + "p" if "x" in res else res
            patterns.append(os.path.join(self.download_dir, f"*part{part_index}*{res_pattern}*"))
        
        return await self._find_files_with_patterns(patterns, ['.m4a', '.aac', '.mp3'])

    async def _find_audio_files(self, part_index, audio_language_info):
        """Find audio files for a specific part based on language info"""
        audio_files = []
        for audio_id, language_suffix in audio_language_info:
            patterns = [
                os.path.join(self.download_dir, f"{self.filename}.part{part_index}.{language_suffix}.*"),
                os.path.join(self.download_dir, f"*part{part_index}*{language_suffix}*"),
                os.path.join(self.download_dir, f"*part{part_index}*{audio_id}*")
            ]
            audio_file = await self._find_files_with_patterns(patterns, ['.mp4', '.mkv', '.webm', '.srt', '.vtt'])
            if audio_file:
                audio_files.append(audio_file)
                logger.info(f"Found audio file for part {part_index}, language {language_suffix}: {audio_file}")

        return list(dict.fromkeys(audio_files))  # Remove duplicates while preserving order

    async def _mux_part(self, part_index, video_file, audio_files):
        """Mux video and audio files for a single part"""
        if not video_file:
            logger.error(f"No video file found for part {part_index}")
            return None

        if not audio_files:
            logger.warning(f"No audio files found for part {part_index}, using video only")
            return video_file

        muxed_file = os.path.join(self.download_dir, f"{self.filename}.part{part_index}.muxed.mkv")
        try:
            logger.info(f"Muxing part {part_index} with {len(audio_files)} audio tracks")
            await self._merge_streams(video_file, audio_files, muxed_file)
            return muxed_file if os.path.exists(muxed_file) and os.path.getsize(muxed_file) > 0 else video_file
        except Exception as e:
            logger.error(f"Error muxing part {part_index}: {e}")
            return video_file

    async def _merge_parts_with_mkvmerge(self, part_files):
        """Merge all parts using mkvmerge"""
        user_id = self.identifier.split('_')[0] if '_' in self.identifier else None
        extension = "mp4" if user_id in MP4_USER_IDS else "mkv"
        final_file = os.path.join(self.download_dir, f"{self.filename}.{extension}")

        def extract_part_number(filename):
            for pattern in [r'part(\d+)', r'\.part(\d+)\.', r'[^a-zA-Z]part(\d+)[^a-zA-Z]', r'part(\d+)$']:
                if match := re.search(pattern, filename, re.IGNORECASE):
                    return int(match.group(1))
            logger.warning(f"Could not extract part number from {filename}")
            return 0

        try:
            part_files.sort(key=extract_part_number)
            logger.info(f"Sorted part files: {part_files}")

            cmd = ['mkvmerge', '-o', final_file] + sum([['+', f] if i > 0 else [f] for i, f in enumerate(part_files)], [])
            logger.info(f"Merging all parts with command: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Failed to merge parts: {stderr.decode()}")
                return None

            logger.info(f"Successfully merged all parts to {final_file}")
            self.final_merged_path = final_file
            return final_file
        except Exception as e:
            logger.error(f"Error during merge: {str(e)}")
            return None

    async def execute(self):
        """Execute the download process for all parts, retrying only failed parts and skipping already muxed ones."""
        await self._check_and_delete_existing_files()
        self.progress_data = self._init_progress_data()
        download_progress.update_progress(self.identifier, self.progress_data)

        try:
            muxed_part_files = []
            selected_audio_streams = await self._get_selected_audio_streams()
            audio_language_info = await self._get_audio_language_suffixes(selected_audio_streams)
            RETRY_LIMIT = 2

            for part_index, part_info in sorted(self.parts.items(), key=lambda x: int(x[0])):
                self.current_part = int(part_index)
                logger.info(f"Processing part {self.current_part} of {self.total_parts}")

                muxed_file = os.path.join(self.download_dir, f"{self.filename}.part{part_index}.muxed.mkv")
                if os.path.exists(muxed_file) and os.path.getsize(muxed_file) > 0:
                    logger.info(f"Muxed file for part {part_index} already exists, skipping download.")
                    muxed_part_files.append(muxed_file)
                    continue

                for attempt in range(1, RETRY_LIMIT + 2):
                    logger.info(f"Attempt {attempt} for part {part_index}")
                    self.processes = []
                    # Download video
                    video_cmd = await self._build_video_command(part_index, part_info)
                    await self._execute_download(video_cmd, f"video_part{part_index}")
                    # Download audios
                    for audio_id, language_suffix in audio_language_info:
                        audio_cmd = await self._build_audio_command(part_index, part_info, audio_id, language_suffix)
                        await self._execute_download(audio_cmd, f"audio_{language_suffix}_part{part_index}")
                    # Monitor
                    await asyncio.gather(*[self._monitor_progress(process, stream_type, part_index)
                                           for process, stream_type in self.processes])
                    self.processes = []
                    # Find files
                    video_file = await self._find_video_file(part_index)
                    if not video_file:
                        logger.error(f"No video file found for part {part_index}")
                        if attempt > RETRY_LIMIT:
                            return 1
                        else:
                            continue
                    audio_files = await self._find_audio_files(part_index, audio_language_info)
                    muxed_file = await self._mux_part(part_index, video_file, audio_files)
                    if muxed_file and os.path.exists(muxed_file) and os.path.getsize(muxed_file) > 0:
                        muxed_part_files.append(muxed_file)
                        logger.info(f"Added muxed file for part {part_index}: {muxed_file}")
                        await self._cleanup([f for f in [video_file] + audio_files if f != muxed_file])
                        break
                    else:
                        logger.error(f"Failed to mux part {part_index}")
                        if attempt > RETRY_LIMIT:
                            return 1
                        # else: retry

            # Set final progress
            if self.progress_data:
                for key in ['video'] + list(self.progress_data.get('audio', {}).keys()):
                    if key == 'video':
                        self.progress_data[key]['percentage'] = 100
                    else:
                        self.progress_data['audio'][key]['percentage'] = 100
                download_progress.update_progress(self.identifier, self.progress_data)
                await self._update_progress_json(force=True)

            # Handle final file
            if len(muxed_part_files) == 1:
                final_file = os.path.join(self.download_dir, f"{self.filename}.mkv")
                try:
                    shutil.copy2(muxed_part_files[0], final_file)
                    if os.path.exists(final_file) and os.path.getsize(final_file) > 0:
                        self.final_merged_path = final_file
                        await self._cleanup(muxed_part_files)
                        return 0
                except Exception as e:
                    logger.error(f"Error creating final file: {e}")
                    return 1
            else:
                final_file = await self._merge_parts_with_mkvmerge(muxed_part_files)
                if not final_file:
                    return 1
                await self._cleanup(muxed_part_files)
                return 0

            logger.error("No muxed part files to merge")
            return 1

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return 1

    async def get_stderr(self):
        """Get stderr from all processes."""
        stderr_data = []
        for process, stream_type in self.processes:
            if process.stderr:
                stderr = await process.stderr.read()
                if stderr:
                    stderr_data.append(f"{stream_type}: {stderr.decode()}")
        return "\n".join(stderr_data).encode() if stderr_data else None

async def periodic_dump_cleanup():
    while True:
        try:
            # Skip cleanup if dumping is disabled
            if not DUMP_STREAMS:
                await asyncio.sleep(3600)  # Sleep for an hour and check again
                continue
                
            record_path = os.path.join("data", "stream_records.json")
            dumps_dir = os.path.join("data", "dumps")
            now = time.time()
            cutoff = now - 48 * 3600  # 48 hours in seconds
            changed = False
            try:
                with open(record_path, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []
            new_records = []
            for rec in records:
                fpath = rec.get("file_path")
                timestamp = rec.get("timestamp")
                
                # Skip records without timestamp (old records) or missing files
                if not timestamp or not fpath or not os.path.exists(fpath):
                    changed = True
                    continue
                
                # Check if file is older than 48 hours
                if timestamp < cutoff:
                    try:
                        os.remove(fpath)
                        changed = True
                        continue  # skip adding to new_records
                    except Exception as e:
                        logger.error(f"Error removing old file {fpath}: {e}")
                        # Keep the record if file couldn't be deleted
                        new_records.append(rec)
                else:
                    new_records.append(rec)
            
            if changed:
                with open(record_path, "w", encoding="utf-8") as f:
                    json.dump(new_records, f, indent=2)
        except Exception as e:
            logger.error(f"Error in periodic_dump_cleanup: {e}")
        await asyncio.sleep(20 * 60)  # 20 minutes
