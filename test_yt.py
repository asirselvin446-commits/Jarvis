import urllib.request
import urllib.parse
import re
import webbrowser

query = "shape of you ed sheeran"
encoded = urllib.parse.quote_plus(query)
search_url = f"https://www.youtube.com/results?search_query={encoded}"

try:
    req = urllib.request.Request(
        search_url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
    video_ids = re.findall(r"watch\?v=(\S{11})", html)
    print("Found video IDs:", video_ids[:3])
    if video_ids:
        play_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
        print(f"Playing video URL: {play_url}")
except Exception as e:
    print(f"Error: {e}")
