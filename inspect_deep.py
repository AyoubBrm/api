
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

try:
    api = YouTubeTranscriptApi()
    if hasattr(api, '_fetcher'):
        fetcher = api._fetcher
        print("Fetcher type:", type(fetcher))
        print("Fetcher vars:", vars(fetcher))
        if hasattr(fetcher, '_http_client'):
             print("Fetcher http client:", fetcher._http_client)
             if hasattr(fetcher._http_client, 'session'):
                 print("Found session in fetcher._http_client.session")

except Exception as e:
    print("Error:", e)
