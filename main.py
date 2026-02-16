"""
YouTube Transcript API Microservice

A production-ready FastAPI microservice that retrieves transcripts from YouTube videos.
Uses youtube_transcript_api with proxy support, retry mechanism, and YouTube's built-in translation.
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List
from youtube_transcript_api import YouTubeTranscriptApi
from fake_useragent import UserAgent
from fastapi import FastAPI, HTTPException
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

# Create dedicated thread pool for transcript operations (non-blocking)
transcript_executor = ThreadPoolExecutor(max_workers=10)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Create API instance (no proxies)
ytt_api = YouTubeTranscriptApi()

# Max retries for getting a good request/handling rate limits
MAX_RETRIES = 5

# Initialize UserAgent
ua = UserAgent()

def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def snippet_to_dict(snippet) -> Dict[str, Any]:
    """Convert FetchedTranscriptSnippet to dictionary."""
    return {
        'text': snippet.text,
        'start': snippet.start,
        'duration': snippet.duration
    }


def fetch_transcript_with_retry(video_id: str, target_language: str, max_retries: int = MAX_RETRIES):
    """
    Fetch transcript with retry mechanism and rotating User-Agents.
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Generate and set new User-Agent for this attempt
            # Rotate between Chrome, Firefox, and Opera
            browser_type = ['chrome', 'firefox', 'opera'][attempt % 3]
            try:
                new_ua = getattr(ua, browser_type)
            except Exception:
                # Fallback to random if specific type fails
                new_ua = ua.random

            # Access internal session to update headers
            # Note: _fetcher and _http_client are internal attributes, but necessary here
            if hasattr(ytt_api, '_fetcher') and hasattr(ytt_api._fetcher, '_http_client'):
                 ytt_api._fetcher._http_client.headers['User-Agent'] = new_ua
                 logger.info(f"Attempt {attempt + 1}/{max_retries} - using User-Agent ({browser_type}): {new_ua[:30]}...")
            
            # List available transcripts
            transcript_list = ytt_api.list(video_id)
            
            # Try to find a transcript
            transcript_obj = None
            actual_language = target_language
            
            # First, try to get transcript in target language directly
            try:
                transcript_obj = transcript_list.find_manually_created_transcript([target_language])
                logger.info(f"Found manual transcript in {target_language}")
            except:
                try:
                    transcript_obj = transcript_list.find_generated_transcript([target_language])
                    logger.info(f"Found auto-generated transcript in {target_language}")
                except:
                    pass
            
            # If not found in target language, get any transcript and try to translate
            if transcript_obj is None:
                try:
                    transcript_obj = transcript_list.find_manually_created_transcript(['en'])
                    logger.info("Found manual English transcript")
                except:
                    try:
                        transcript_obj = transcript_list.find_generated_transcript(['en'])
                        logger.info("Found auto-generated English transcript")
                    except:
                        for t in transcript_list:
                            transcript_obj = t
                            logger.info(f"Using transcript in {t.language_code}")
                            break
                
                # Try to translate to target language
                if transcript_obj and target_language != transcript_obj.language_code:
                    try:
                        logger.info(f"Translating to {target_language}...")
                        transcript_obj = transcript_obj.translate(target_language)
                    except Exception as translate_error:
                        # Translation not available - return original language instead
                        logger.warning(f"Translation not available: {translate_error}")
                        logger.info(f"Returning transcript in original language: {transcript_obj.language_code}")
                        actual_language = transcript_obj.language_code
            
            if transcript_obj is None:
                raise Exception("No transcript found")
            
            # Fetch the segments
            fetched_transcript = transcript_obj.fetch()
            
            # Convert to dict
            segments = [snippet_to_dict(snippet) for snippet in fetched_transcript]
                
            logger.info(f"Success! Fetched {len(segments)} segments")
            
            return segments, actual_language
            
        except Exception as e:
            # Don't retry if it's a translation issue - that won't change
            if "not translatable" in str(e).lower():
                raise e
            last_error = e
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
    
    raise last_error

@app.get("/transcript", tags=["Transcript"], response_model={})
async def transcript(video_url: str, target_language: str = "en"):
    """
    Get YouTube video transcript.
    
    - **video_url**: YouTube video URL or video ID
    - **target_language**: Target language code (e.g., 'en', 'es', 'fr'). Default is 'en'.
    """
    try:
        # Extract video ID
        video_id = extract_video_id(video_url)
        logger.info(f"Fetching transcript for video: {video_id}")
        logger.info(f"Target language: {target_language}")
        
        try:
            # Run blocking transcript fetch in thread pool
            loop = asyncio.get_event_loop()
            segments, actual_language = await loop.run_in_executor(
                transcript_executor, 
                fetch_transcript_with_retry, 
                video_id, 
                target_language
            )
        except Exception as e:
            logger.error(f"Failed after {MAX_RETRIES} retries: {e}")
            raise HTTPException(status_code=200, detail="Sorry, a transcript isn't available for this video.")
        
        # Build full transcript text
        full_transcript = " ".join([seg['text'] for seg in segments])
        
        
        return {
            "transcript": full_transcript,
            "segments": segments,
            "language": actual_language,
            "requested_language": target_language,
            "video_id": video_id
        }
    
    except ValueError as e:
        raise HTTPException(status_code=200, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=200, detail=str(e))

# --- YouTube Search Feature (yt-dlp with Caching Cursor) ---
import hashlib
from cachetools import TTLCache


# High-performance cache: 500 searches, 15 minute TTL
SEARCH_CACHE = TTLCache(maxsize=500, ttl=900)
BATCH_SIZE = 200  # Fetch 200 videos per search

# Dedicated thread pool for search operations (non-blocking)
search_executor = ThreadPoolExecutor(max_workers=10)


def generate_search_id(query: str) -> str:
    """Generate a unique search ID based on query and timestamp."""
    return hashlib.md5(f"{query}:{time.time()}".encode()).hexdigest()[:12]


def parse_cursor(cursor: str) -> tuple:
    """Parse cursor string into (search_id, offset)."""
    try:
        parts = cursor.split(":")
        return parts[0], int(parts[1])
    except (ValueError, IndexError):
        raise ValueError("Invalid cursor format")


def search_youtube_ytdlp(query: str, limit: int) -> List[Dict[str, Any]]:
    """Search YouTube using yt-dlp - runs in separate thread."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'socket_timeout': 30,
    }
    
    search_query = f"ytsearch{limit}:{query}"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(search_query, download=False)
    
    videos = []
    if result and 'entries' in result:
        for entry in result['entries']:
            if entry:
                # Format duration
                duration_seconds = entry.get('duration') or 0
                if duration_seconds:
                    minutes, seconds = divmod(int(duration_seconds), 60)
                    hours, minutes = divmod(minutes, 60)
                    if hours > 0:
                        duration_formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
                    else:
                        duration_formatted = f"{minutes}:{seconds:02d}"
                else:
                    duration_formatted = "N/A"
                
                videos.append({
                    'video_id': entry.get('id'),
                    'title': entry.get('title'),
                    'channel': entry.get('channel') or entry.get('uploader'),
                    'duration': duration_formatted,
                    'duration_seconds': duration_seconds,
                    'views': entry.get('view_count'),
                    'thumbnail': entry.get('thumbnail') or f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg",
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}"
                })
    
    return videos


@app.get("/search", tags=["Search"])
async def search_youtube(query: str = None, cursor: str = None, limit: int = 50):
    """
    Search YouTube videos with caching cursor pagination.
    
    - **query**: Search query string (required for new search)
    - **cursor**: Cursor token for pagination (from previous response)
    - **limit**: Results per page (default: 50)
    """
    try:
        # Validate limit
        if limit < 1:
            limit = 1
        elif limit > 100:
            limit = 100
        
        cached = False
        offset = 0
        search_id = None
        all_videos = []
        
        if cursor:
            # Pagination request - get from cache (instant)
            search_id, offset = parse_cursor(cursor)
            cache_data = SEARCH_CACHE.get(search_id)
            
            if not cache_data:
                raise HTTPException(
                    status_code=200, 
                    detail="Cursor expired or invalid. Please start a new search."
                )
            
            all_videos = cache_data["videos"]
            query = cache_data["query"]
            cached = True
            logger.info(f"Cache hit: search_id={search_id}, offset={offset}")
            
        elif query:
            # New search - fetch batch and cache
            search_id = generate_search_id(query)
            logger.info(f"New search: '{query}' (search_id={search_id}, batch={BATCH_SIZE})")
            
            # Run in dedicated thread pool - non-blocking for other requests
            loop = asyncio.get_event_loop()
            all_videos = await loop.run_in_executor(
                search_executor, 
                search_youtube_ytdlp, 
                query, 
                BATCH_SIZE
            )
            
            # Cache results for fast subsequent access
            SEARCH_CACHE[search_id] = {
                "query": query,
                "videos": all_videos
            }
            logger.info(f"Cached {len(all_videos)} videos (search_id={search_id})")
            
        else:
            raise HTTPException(
                status_code=200, 
                detail="Either 'query' or 'cursor' parameter is required"
            )
        
        # Get slice for current page
        videos = all_videos[offset:offset + limit]
        
        # Calculate next/prev cursors
        next_offset = offset + limit
        next_cursor = f"{search_id}:{next_offset}" if next_offset < len(all_videos) else None
        
        prev_cursor = None
        if offset > 0:
            prev_offset = max(0, offset - limit)
            prev_cursor = f"{search_id}:{prev_offset}"
        
        return {
            "query": query,
            "count": len(videos),
            "offset": offset,
            "limit": limit,
            "next_cursor": next_cursor,
            "prev_cursor": prev_cursor,
            "videos": videos
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=200, detail=f"Search failed: {str(e)}")


# --- MP3 Conversion Feature ---
import os
import yt_dlp
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.background import BackgroundTasks

# Thread pool for async video downloads
# Thread pool for async video downloads
# Increased from 4 to 16 to handle higher concurrency
executor = ThreadPoolExecutor(max_workers=16)

# Ensure downloads directory exists at startup
os.makedirs("downloads", exist_ok=True)

# Timeout for download operations (seconds)
DOWNLOAD_TIMEOUT = 300  # 5 minutes max

def cleanup_file(path: str):
    """Delete file after response is sent."""
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Cleaned up file: {path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {path}: {e}")


def sanitize_filename(name: str) -> str:
    """Sanitize filename and ensure .mp3 extension."""
    # Remove any directory components
    name = os.path.basename(name)
    
    # Remove problematic characters
    for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        name = name.replace(char, '_')
    
    # Ensure .mp3 extension
    if not name.lower().endswith('.mp3'):
        name = f"{name}.mp3"
    
    return name


def download_video_sync(video_url: str, output_path: str) -> bool:
    """Synchronous video download function for thread pool execution."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path.replace('.mp3', '.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 3,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    
    return True


@app.post("/convert", tags=["Conversion"])
async def convert_to_mp3(video_url: str, background_tasks: BackgroundTasks):
    """
    Download YouTube video and convert to MP3.
    Returns the MP3 file.
    
    - **video_url**: YouTube video URL or video ID
    
    Example: `curl "API_URL/convert?video_url=VIDEO_URL"`
    """
    try:
        # Extract and validate video ID
        video_id = extract_video_id(video_url)
        
        # Reconstruct clean URL to strip playlist/mix parameters
        # This ensures we only download the specific video, not the whole playlist
        clean_video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        logger.info(f"Converting video: {video_id} to MP3")
        
        # Use video ID as filename
        output_filename = f"{video_id}.mp3"
        
        # Generate unique internal filename to avoid conflicts
        unique_id = uuid.uuid4().hex[:8]
        internal_file = f"downloads/{video_id}_{unique_id}.mp3"
        
        # Download with timeout protection
        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(executor, download_video_sync, clean_video_url, internal_file),
                timeout=DOWNLOAD_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"Download timeout for video: {video_id}")
            raise HTTPException(status_code=200, detail="Download timeout - video may be too long or network is slow")
        
        # Verify file exists
        if not os.path.exists(internal_file):
            logger.error(f"Output file not found: {internal_file}")
            raise HTTPException(status_code=200, detail="Conversion failed: Output file not found")
        
        # Schedule cleanup after response
        background_tasks.add_task(cleanup_file, internal_file)
        
        logger.info(f"Conversion complete: {video_id} -> {output_filename}")
        
        return FileResponse(
            path=internal_file,
            filename=output_filename,
            media_type="audio/mpeg"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=200, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        raise HTTPException(status_code=200, detail=f"Conversion failed: {str(e)}")

