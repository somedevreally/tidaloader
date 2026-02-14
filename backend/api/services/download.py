from pathlib import Path
import asyncio
import aiohttp
import traceback

from api.utils.logging import log_error, log_info, log_step, log_success, log_warning
from api.services.audio import transcode_to_mp3, transcode_to_opus, write_metadata_tags
from api.services.files import organize_file_by_metadata
from api.services.beets import run_beets_import
from api.services.lyrics import embed_lyrics_with_ffmpeg
from api.services.musicbrainz import enhance_metadata_with_musicbrainz
from queue_manager import queue_manager

async def download_file_async(
    track_id: int, 
    stream_url: str, 
    filepath: Path, 
    filename: str, 
    metadata: dict = None,
    organization_template: str = "{Artist}/{Album}/{TrackNumber} - {Title}",
    group_compilations: bool = True,
    run_beets: bool = False,
    embed_lyrics: bool = False,
    use_musicbrainz: bool = True
):
    processed_path = filepath
    try:
        log_step("3/4", f"Downloading {filename}...")
        
        queue_manager.update_active_progress(track_id, 0, 'downloading')
        
        # Use generous timeouts for large FLAC files
        timeout = aiohttp.ClientTimeout(
            total=1800,      # 30 minutes total
            connect=30,      # 30 seconds to connect
            sock_read=120    # 2 minutes per chunk read
        )
        
        async with aiohttp.ClientSession() as session:
            async with session.get(stream_url, timeout=timeout) as response:
                if response.status != 200:
                    error_msg = f"HTTP {response.status}"
                    log_error(f"Download failed: {error_msg}")
                    queue_manager.update_active_progress(track_id, 0, 'failed')
                    queue_manager.mark_failed(track_id, error_msg)
                    return
                
                # Validate content-type to detect XML error responses
                content_type = response.headers.get('content-type', '').lower()
                if 'xml' in content_type or 'text' in content_type:
                    error_msg = f"Invalid content type: {content_type} (likely quality unavailable)"
                    log_error(f"Download failed: {error_msg}")
                    queue_manager.update_active_progress(track_id, 0, 'failed')
                    queue_manager.mark_failed(track_id, error_msg)
                    return
                
                total_size = int(response.headers.get('content-length', 0))
                
                # Additional validation: tiny files are likely errors
                if total_size > 0 and total_size < 10000:
                    content_preview = await response.content.read(500)
                    if content_preview.startswith(b'<?xml') or b'<Error>' in content_preview:
                        error_msg = "Received error response instead of audio (quality likely unavailable)"
                        log_error(f"Download failed: {error_msg}")
                        queue_manager.update_active_progress(track_id, 0, 'failed')
                        queue_manager.mark_failed(track_id, error_msg)
                        return
                    error_msg = f"File too small ({total_size} bytes), likely invalid"
                    log_error(f"Download failed: {error_msg}")
                    queue_manager.update_active_progress(track_id, 0, 'failed')
                    queue_manager.mark_failed(track_id, error_msg)
                    return
                
                downloaded = 0
                
                # Ensure the directory exists
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                with open(filepath, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                progress = int((downloaded / total_size) * 100)
                                queue_manager.update_active_progress(track_id, progress, 'downloading')
                            
                            await asyncio.sleep(0.01)
        
        if metadata:
            if metadata.get('target_format') == 'mp3':
                bitrate = metadata.get('bitrate_kbps', 256)
                mp3_path = filepath.with_suffix('.mp3')
                log_step("3.5/4", f"Transcoding to MP3 ({bitrate} kbps)...")
                queue_manager.update_active_progress(track_id, 95, 'transcoding')
                await transcode_to_mp3(filepath, mp3_path, bitrate)
                processed_path = mp3_path
                metadata['file_ext'] = '.mp3'
                try:
                    filepath.unlink()
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    log_warning(f"Failed to remove intermediate file: {exc}")
            elif metadata.get('target_format') == 'opus':
                bitrate = metadata.get('bitrate_kbps', 192)
                opus_path = filepath.with_suffix('.opus')
                log_step("3.5/4", f"Transcoding to Opus ({bitrate} kbps)...")
                queue_manager.update_active_progress(track_id, 95, 'transcoding')
                await transcode_to_opus(filepath, opus_path, bitrate)
                processed_path = opus_path
                metadata['file_ext'] = '.opus'
                try:
                    filepath.unlink()
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    log_warning(f"Failed to remove intermediate file: {exc}")
            else:
                processed_path = filepath
                metadata.setdefault('file_ext', filepath.suffix)
        
        if metadata:
            # Enhance metadata with MusicBrainz for comprehensive tagging (if enabled)
            if use_musicbrainz:
                log_step("4/4", "Enhancing metadata with MusicBrainz...")
                try:
                    metadata = await enhance_metadata_with_musicbrainz(metadata)
                except Exception as e:
                    log_warning(f"MusicBrainz enhancement failed: {e}")
            
            log_step("4/4", "Writing metadata tags...")
            await write_metadata_tags(processed_path, metadata)
            
            if embed_lyrics:
                await embed_lyrics_with_ffmpeg(processed_path, metadata)
        
        # Organize file
        log_step("4/4", "Organizing file...")
        final_path = await organize_file_by_metadata(
            processed_path, 
            metadata,
            template=organization_template,
            group_compilations=group_compilations
        )
        
        # Run beets import if requested
        if run_beets:
            await run_beets_import(final_path)
            
        # Update state to completed
        if metadata is None:
            metadata = {}
        metadata['final_path'] = str(final_path)
        
        # Mark completed in queue manager (which also records to DB library tables)
        queue_manager.mark_completed(track_id, final_path.name, metadata)
        
        file_size_mb = final_path.stat().st_size / 1024 / 1024
        display_name = final_path.name if final_path else filename
        log_success(f"Downloaded: {display_name} ({file_size_mb:.2f} MB)")
        log_info(f"Location: {final_path}")
        
        # Invalidate library cache so the new file/tags appear immediately
        try:
             from api.services.library import library_service
             library_service.invalidate_cache()
        except Exception as e:
             log_warning(f"Failed to invalidate library cache: {e}")

        print(f"{'='*60}\n")
        
    except Exception as e:
        log_error(f"Download error: {e}")
        traceback.print_exc()
        
        queue_manager.mark_failed(track_id, str(e))
        
        if filepath.exists():
            try:
                filepath.unlink()
                log_info(f"Cleaned up partial file: {filename}")
            except Exception:
                pass
        
        if processed_path and processed_path != filepath and processed_path.exists():
            try:
                processed_path.unlink()
                log_info(f"Cleaned up partial file: {processed_path.name}")
            except Exception:
                pass
