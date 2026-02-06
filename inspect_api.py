
import sys
from youtube_transcript_api import YouTubeTranscriptApi

print("Type:", type(YouTubeTranscriptApi))
print("Dir:", dir(YouTubeTranscriptApi))
try:
    instance = YouTubeTranscriptApi()
    print("Instance Dir:", dir(instance))
except Exception as e:
    print("Instantiation failed:", e)

# Check if there is a 'list_transcripts' method on the class or instance
if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
    print("Has static list_transcripts")

