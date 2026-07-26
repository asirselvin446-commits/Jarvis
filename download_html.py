import os
import urllib.request

url = "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzM2ZTNmMzc0MjJmMzRmZjBhNzBmNzg1ODM1ZmU5ODE4EgsSBxDt6s3hvwsYAZIBIwoKcHJvamVjdF9pZBIVQhM2NjQwNjAxMDczODIxMDE0NDM2&filename=&opi=96797242"
os.makedirs("ui/templates", exist_ok=True)
urllib.request.urlretrieve(url, "ui/templates/index.html")
print("Downloaded index.html")
