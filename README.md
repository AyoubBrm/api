# API Overview

A YouTube API for retrieving YouTube video transcripts and converting videos to MP3.

## 🎯 API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/transcript` | GET | Get video transcript with timing |
| `/convert` | GET | Download video as MP3 |

##  Endpoints

### 1. Get Transcript
**GET** `/transcript?video_url={URL}&target_language={LANG}`

**Parameters:**
- `video_url` (required): YouTube URL or video ID
- `target_language` (optional): Language code (default: `en`)

**Example:**
```bash
curl "http://localhost:8000/transcript?video_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**Response:**
```json
{
  "transcript": "Full transcript text...",
    "segments": [
      {"text": "Hello", "start": 0.0, "duration": 2.5},
      {"text": "World", "start": 2.5, "duration": 1.8}
    ],
    "language": "en",
    "requested_language": "en",
    "video_id": "dQw4w9WgXcQ"
}
```

---

### 2. Convert to MP3
**GET** `/convert?video_url={URL}`

Downloads YouTube video and returns MP3 audio file.

**Example:**
```bash
curl "http://localhost:8000/convert?video_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ" --output your_file_name.mp3

```


## ⚠️ Error Handling

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Invalid YouTube URL |
| 404 | Transcript not available |
| 500 | Server error |

**Example error response:**
```json
{
  "detail": "Sorry, a transcript isn't available for this video."
}
```
