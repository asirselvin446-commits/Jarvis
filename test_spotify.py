import os
import webbrowser
import urllib.parse

query = "shape of you"
encoded = urllib.parse.quote(query)

# Test 1: spotify: URI protocol
uri = f"spotify:search:{encoded}"
print(f"Testing Spotify URI: {uri}")

# Test 2: Web URL
url = f"https://open.spotify.com/search/{encoded}"
print(f"Testing Spotify Web URL: {url}")
