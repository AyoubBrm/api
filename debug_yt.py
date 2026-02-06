
import logging
from fake_useragent import UserAgent
import yt_dlp
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_subs():
    video_url = "https://www.youtube.com/watch?v=_8Probyi86w"
    target_language = "es"
    
    ua = UserAgent()
    user_agent = ua.random
    
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True, 
        'writeautomaticsub': True,
        'quiet': True,
        'subtitleslangs': [target_language, 'en'],
        'http_headers': {'User-Agent': user_agent}
    }

    print(f"Testing with target_language: {target_language}")
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            
            subs = info.get('subtitles', {})
            auto_subs = info.get('automatic_captions', {})
            
            print("\n--- Subtitles (Manual) ---")
            print(list(subs.keys()))
            
            print("\n--- Automatic Captions (Auto) ---")
            print(list(auto_subs.keys()))
            
            if 'en' in auto_subs:
                print("\n--- URL for 'en' ---")
                print(auto_subs['en'][0]['url'])

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    debug_subs()
