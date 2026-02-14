from pathlib import Path
from api.utils.logging import log_info, log_success, log_warning, log_step
import asyncio
import shutil
from lyrics_client import lyrics_client

async def fetch_and_store_lyrics(filepath: Path, metadata: dict, audio_file=None, is_mp3=False):
    """
    Fetch and store lyrics for an audio file.
    - Synced lyrics: Save as .lrc file + SYNCEDLYRICS tag (FLAC/Opus) or SYLT (MP3)
    - Plain lyrics: Embed in LYRICS tag (FLAC/Opus) or USLT (MP3)
    """
    if metadata.get('title') and metadata.get('artist'):
        try:
            log_info("Fetching lyrics...")
            lyrics_result = await lyrics_client.get_lyrics(
                track_name=metadata['title'],
                artist_name=metadata['artist'],
                album_name=metadata.get('album'),
                duration=metadata.get('duration')
            )
            
            if lyrics_result:
                if lyrics_result.synced_lyrics:
                    metadata['synced_lyrics'] = lyrics_result.synced_lyrics
                    # Save synced lyrics to .lrc sidecar file (most compatible)
                    lrc_path = filepath.with_suffix('.lrc')
                    try:
                        with open(lrc_path, 'w', encoding='utf-8') as f:
                            f.write(lyrics_result.synced_lyrics)
                        log_success(f"Saved synced lyrics to {lrc_path.name}")
                    except Exception as e:
                        log_warning(f"Failed to save .lrc file: {e}")
                    
                    # Embed in tags (SYNCEDLYRICS for FLAC/Opus, SYLT for MP3)
                    if is_mp3:
                        try:
                            from mutagen.mp3 import MP3
                            from mutagen.id3 import ID3, SYLT, Encoding
                            audio = MP3(str(filepath), ID3=ID3)
                            if audio.tags is None:
                                audio.add_tags()
                            
                            # Parse LRC format and create SYLT
                            lines = []
                            for line in lyrics_result.synced_lyrics.split('\n'):
                                # LRC format: [mm:ss.xx]text
                                if line.startswith('[') and ']' in line:
                                    timestamp_part = line[1:line.index(']')]
                                    text_part = line[line.index(']')+1:]
                                    if ':' in timestamp_part and text_part.strip():
                                        try:
                                            parts = timestamp_part.split(':')
                                            minutes = int(parts[0])
                                            seconds = float(parts[1])
                                            milliseconds = int((minutes * 60 + seconds) * 1000)
                                            lines.append((text_part, milliseconds))
                                        except (ValueError, IndexError):
                                            continue
                            
                            if lines:
                                audio.tags.delall('SYLT')
                                audio.tags.add(SYLT(
                                    encoding=Encoding.UTF8,
                                    lang='eng',
                                    format=2,  # milliseconds
                                    type=1,    # lyrics
                                    text=lines
                                ))
                                audio.save()
                                log_success("Embedded synced lyrics in SYLT frame")
                        except Exception as e:
                            log_warning(f"Failed to embed MP3 SYLT: {e}")
                    elif audio_file:
                        try:
                            audio_file['LYRICS'] = lyrics_result.synced_lyrics
                            log_success("Embedded synced lyrics in LYRICS tag")
                        except Exception as e:
                            log_warning(f"Failed to embed synced lyrics tag: {e}")
                            
                elif lyrics_result.plain_lyrics:
                    metadata['plain_lyrics'] = lyrics_result.plain_lyrics
                    
                    # Embed plain lyrics
                    if is_mp3:
                        try:
                            from mutagen.mp3 import MP3
                            from mutagen.id3 import ID3, USLT, Encoding
                            audio = MP3(str(filepath), ID3=ID3)
                            if audio.tags is None:
                                audio.add_tags()
                            
                            audio.tags.delall('USLT')
                            audio.tags.add(USLT(
                                encoding=Encoding.UTF8,
                                lang='eng',
                                desc='',
                                text=lyrics_result.plain_lyrics
                            ))
                            audio.save()
                            log_success("Embedded plain lyrics in USLT frame")
                        except Exception as e:
                            log_warning(f"Failed to embed MP3 USLT: {e}")
                    elif audio_file:
                        try:
                            audio_file['LYRICS'] = lyrics_result.plain_lyrics
                            log_success("Embedded plain lyrics in LYRICS tag")
                        except Exception as e:
                            log_warning(f"Failed to embed plain lyrics tag: {e}")
                
        except Exception as e:
            log_warning(f"Failed to fetch lyrics: {e}")

async def embed_lyrics_with_ffmpeg(filepath: Path, metadata: dict):
    """Embed lyrics into the audio file using FFmpeg"""
    try:
        import subprocess
        

        try:
            subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            log_warning("FFmpeg not found. Skipping lyrics embedding.")
            return

        lyrics = metadata.get('synced_lyrics') or metadata.get('plain_lyrics')
        if not lyrics:
            log_info("No lyrics found to embed.")
            return

        log_step("3.8/4", f"Embedding lyrics with FFmpeg...")
        

        lyrics_path = filepath.with_suffix('.lyrics.txt')
        with open(lyrics_path, 'w', encoding='utf-8') as f:
            f.write(lyrics)
            
        output_path = filepath.with_suffix('.temp' + filepath.suffix)
        

        cmd = [
            "ffmpeg", "-y", "-i", str(filepath),
            "-map", "0", "-c", "copy",
            "-metadata", f"LYRICS={lyrics}",
            str(output_path)
        ]
        

        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:

            shutil.move(str(output_path), str(filepath))
            log_success("Lyrics embedded with FFmpeg")
        else:
            log_warning(f"FFmpeg lyrics embedding failed: {stderr.decode()}")
            if output_path.exists():
                output_path.unlink()
                

        if lyrics_path.exists():
            lyrics_path.unlink()
            
    except Exception as e:
        log_warning(f"Failed to embed lyrics with FFmpeg: {e}")
        import traceback
        traceback.print_exc()
