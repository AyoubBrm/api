"""
YouTube Transcript API Microservice

A production-ready FastAPI microservice that retrieves transcripts from YouTube videos.
Uses youtube_transcript_api with proxy support, retry mechanism, and YouTube's built-in translation.
"""

import logging
import re
import time
from typing import Any, Dict, List
from youtube_transcript_api import YouTubeTranscriptApi
from fake_useragent import UserAgent
from fastapi import FastAPI, HTTPException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Create API instance (no proxies)
ytt_api = YouTubeTranscriptApi()

# Max retries for getting a good request/handling rate limits
MAX_RETRIES = 10

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
            segments, actual_language = fetch_transcript_with_retry(video_id, target_language)
        except Exception as e:
            logger.error(f"Failed after {MAX_RETRIES} retries: {e}")
            raise HTTPException(status_code=404, detail="Sorry, a transcript isn't available for this video.")
        
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
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- MP3 Conversion Feature ---
import os
import yt_dlp
import static_ffmpeg
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.background import BackgroundTasks

# Ensure ffmpeg/ffprobe paths are set
static_ffmpeg.add_paths()

def cleanup_file(path: str):
    """Delete file after response is sent."""
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Cleaned up file: {path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {path}: {e}")

@app.get("/convert", tags=["Conversion"])
async def convert_to_mp3(video_url: str, background_tasks: BackgroundTasks):
    """
    Download YouTube video and convert to MP3.
    Returns the MP3 file.
    """
    try:
        video_id = extract_video_id(video_url)
        logger.info(f"Converting video: {video_id} to MP3")
        
        # Configure yt-dlp
        output_template = f"downloads/{video_id}.%(ext)s"
        mp3_file = f"downloads/{video_id}.mp3"
        
        # Ensure downloads dir exists
        os.makedirs("downloads", exist_ok=True)
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        
        # Download and convert
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
            
        if not os.path.exists(mp3_file):
            raise HTTPException(status_code=500, detail="Conversion failed: Output file not found")
            
        # Schedule cleanup
        background_tasks.add_task(cleanup_file, mp3_file)
        
        return FileResponse(
            path=mp3_file, 
            filename=f"{video_id}.mp3", 
            media_type="audio/mpeg"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Conversion error: {e}")
