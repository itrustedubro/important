import asyncio
import sys
import re

async def parse_formats(url: str):
    try:
        # Run N_m3u8DL-RE command with auto-select to prevent getting stuck
        cmd = ['N_m3u8DL-RE', url, '--skip-download', '--auto-select','--write-meta-json', 'false']
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        videos = []
        audios = []
        seen = set()  # To avoid duplicates
        
        while True:
            try:
                line = await process.stdout.readline()
                if not line:
                    break
                # Use errors='replace' to handle encoding issues
                line = line.decode('utf-8', errors='replace').strip()
                
                # Only process Vid and Aud lines, skip Sub lines
                if 'INFO : Vid' in line:
                    # Remove timestamp and INFO prefix
                    content = ' '.join(line.split()[3:])
                    
                    if content in seen:
                        continue
                    seen.add(content)
                    
                    try:
                        # Parse video info
                        resolution_match = re.search(r'(\d+x\d+)', content)
                        bitrate_match = re.search(r'(\d+)\s*Kbps', content)
                        codec_match = re.search(r'((?:avc1|hvc1|dvh1)\.[0-9A-F.]+)', content)
                        
                        # Safely extract FPS
                        fps = "25"  # Default
                        if '|' in content:
                            parts = content.split('|')
                            if len(parts) > 2:
                                fps_part = parts[2].strip()
                                fps_match = re.search(r'(\d+(?:\.\d+)?)', fps_part)
                                if fps_match:
                                    fps = fps_match.group(1)
                        
                        # Safely extract HDR info
                        hdr = ""
                        hdr_match = re.search(r'\|\s*((?:SDR|HDR|PQ))\s*$', content)
                        if hdr_match:
                            hdr = hdr_match.group(1)
                        
                        if resolution_match and bitrate_match and codec_match:
                            resolution = resolution_match.group(1)
                            bitrate = bitrate_match.group(1)
                            codec = codec_match.group(1)
                            
                            # For new format, use combination of properties as stream ID
                            stream_id = f"{resolution}_{bitrate}_{codec}_{fps}_{hdr}".replace('.', '_')
                            
                            videos.append({
                                'resolution': resolution,
                                'bitrate': bitrate,
                                'codec': codec,
                                'fps': fps,
                                'hdr': hdr,
                                'stream_id': stream_id
                            })
                    except Exception as e:
                        print(f"Error parsing video: {str(e)}", file=sys.stderr)
                    
                elif 'INFO : Aud' in line and '*CENC' not in line:  # Updated to handle new audio format
                    # Remove timestamp and INFO prefix
                    content = ' '.join(line.split()[3:])
                    
                    if content in seen:
                        continue
                    seen.add(content)
                    
                    try:
                        # Parse parts - but keep original stream ID intact
                        parts = content.split('|')
                        
                        # Extract the proper stream ID: remove "Aud " prefix and include only first two parts
                        # Example: "Aud audio-atmos_vod-ak-aoc.tv.apple.com | English | en | 16/JOCCH" 
                        # becomes "audio-atmos_vod-ak-aoc.tv.apple.com | English"
                        first_part = parts[0].strip()
                        if first_part.startswith('Aud '):
                            first_part = first_part[4:]  # Remove 'Aud ' prefix
                        
                        language_name = parts[1].strip() if len(parts) > 1 else ""
                        
                        # The proper stream ID is the first part plus the language name
                        stream_id = f"{first_part} | {language_name}" if language_name else first_part
                        
                        # Get language code (usually in third part)
                        language_code = parts[2].strip() if len(parts) > 2 else ""
                        
                        # Get channel info (usually in fourth part)
                        channels = "2"  # Default
                        if len(parts) > 3:
                            channel_info = parts[3].strip()
                            
                            # Extract channel count - safer handling
                            if "CH" in channel_info:
                                ch_match = re.search(r'(\d+)CH', channel_info)
                                if ch_match:
                                    channels = ch_match.group(1)
                            elif "JOCCH" in channel_info:
                                # Handle Atmos format like "16/JOCCH"
                                ch_parts = channel_info.split('/')
                                if ch_parts and ch_parts[0].isdigit():
                                    channels = ch_parts[0]
                        
                        # Determine bitrate and codec from the stream_id
                        bitrate = "0"
                        codec = "mp4a.40.2"  # Default codec
                        
                        if "stereo-32" in stream_id:
                            bitrate = "32"
                        elif "stereo-64" in stream_id:
                            bitrate = "64"
                        elif "stereo-128" in stream_id:
                            bitrate = "128"
                        elif "stereo-160" in stream_id:
                            bitrate = "160"
                        elif "atmos" in stream_id:
                            bitrate = "768"  # Typical Atmos bitrate
                            codec = "ec-3+atmos"
                        elif "ac3" in stream_id:
                            bitrate = "384"  # Typical AC3 bitrate
                            codec = "ac-3"
                        elif "HE2" in stream_id:
                            bitrate = "32"  # HE-AAC v2 is typically low bitrate
                            codec = "mp4a.40.5"  # HE-AAC v2
                        
                        audios.append({
                            'stream_id': stream_id,
                            'language': language_code,
                            'language_name': language_name,
                            'bitrate': bitrate,
                            'codec': codec,
                            'channels': channels
                        })
                    except Exception as e:
                        print(f"Error parsing audio: {str(e)}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing line: {str(e)}", file=sys.stderr)
        
        # Sort by bitrate
        videos.sort(key=lambda x: int(x['bitrate']), reverse=True)
        audios.sort(key=lambda x: int(x['bitrate']), reverse=True)
        
        # Print organized information
        print("\nVideos:")
        print("-" * 80)
        print(f"{'Resolution':<10} {'Bitrate':>6} {'Codec':<12} {'FPS':>7}  {'HDR':<5}  {'Stream ID'}")
        print("-" * 80)
        for v in videos:
            print(f"{v['resolution']:<10} {v['bitrate']:>4}k {v['codec']:<12} {v['fps']:>5}fps  {v.get('hdr', ''):<5}  {v['stream_id']}")
            
        print("\nAudios:")
        print("-" * 80)
        print(f"{'Lang':>4} {'Name':<25} {'Bitrate':>7} {'Codec':<12} {'Ch':>3}  {'Stream ID'}")
        print("-" * 80)
        for a in audios:
            lang = a['language'].split('-')[0] if a['language'] else ""  # Only take first part of language code
            name = a['language_name'][:25] if a['language_name'] else ""
            print(f"{lang:>4} {name:<25} {a['bitrate']:>5}k {a['codec']:<12} {a['channels']:>2}ch  {a['stream_id']}")
            
        # Proper cleanup
        try:
            # Ensure we read stderr to prevent blocking
            stderr_data = await process.stderr.read()
            # Wait for the process to finish with timeout
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            # If it takes too long, terminate the process
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                process.kill()  # Force kill if still running
        
        # Return the parsed formats
        return {
            'videos': videos,
            'audios': audios
        }
                
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return None

async def main():
    # Get URL from user
    url = input("Enter the URL to parse formats: ").strip()
    
    if not url:
        print("URL cannot be empty", file=sys.stderr)
        return
    
    try:    
        await parse_formats(url)
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
    finally:
        # Ensure proper cleanup of event loop resources
        pending = asyncio.all_tasks()
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

if __name__ == "__main__":
    asyncio.run(main()) 