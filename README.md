# API Overview

A YouTube API for retrieving YouTube video transcripts, searching videos, and converting videos to MP3.

## 🎯 API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/transcript` | GET | Get video transcript with timing |
| `/search` | GET | Search YouTube videos |
| `/convert` | POST | Download video as MP3 |

##  Endpoints

### 1. Get Transcript
**GET** `/transcript?video_url={URL}&target_language={LANG}`

**Parameters:**
- `video_url` (required): YouTube URL or video ID
- `target_language` (optional): Language code (default: `en`)

**Example:**
```bash
curl "https://youtube-api95.p.rapidapi.com/transcript?video_url=https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --header 'x-rapidapi-host: youtube-api95.p.rapidapi.com' \
  --header 'x-rapidapi-key: YOUR_KEY'
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
  "video_id": "dQw4w9WgXcQ"
}
```

---

### 2. Search YouTube
**GET** `/search?query={QUERY}&cursor={CURSOR}&limit={LIMIT}`

Search for YouTube videos with caching cursor pagination.

**Parameters:**
- `query` (required for new search): Search query string
- `cursor` (for pagination): Cursor token from previous response
- `limit` (optional): Results per page (default: 15, max: 50)

**New Search:**
```bash
curl "https://youtube-api95.p.rapidapi.com/search?query=music&limit=15" \
  --header 'x-rapidapi-host: youtube-api95.p.rapidapi.com' \
  --header 'x-rapidapi-key: YOUR_KEY'
```

**Response:**
```json
{
  "query": "music",
  "count": 15,
  "total_cached": 50,
  "cached": false,
  "next_cursor": "abc123:15",
  "prev_cursor": null,
  "videos": [...]
}
```

**Next Page:** Use `next_cursor` from response:
```bash
curl "https://youtube-api95.p.rapidapi.com/search?cursor=abc123:15&limit=15"
```

---

### 3. Convert to MP3
**POST** `/convert?video_url={URL}`

Downloads YouTube video and returns MP3 audio file.

**Parameters:**
- `video_url` (required): YouTube URL or video ID

**Example:**
```bash
curl -X POST "https://youtube-api95.p.rapidapi.com/convert?video_url=https://www.youtube.com/watch?v=Pem6GlpeBWA" \
  --header 'x-rapidapi-host: youtube-api95.p.rapidapi.com' \
  --header 'x-rapidapi-key: YOUR_KEY' \
  --output "song.mp3"
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
