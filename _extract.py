import io
html = open("files.html", encoding="utf-8").read()
lines = html.splitlines()
# main inline <script> is line 140 (1-indexed) to 1112 inclusive
content = "\n".join(lines[140:1111])
open("_check.mjs", "w", encoding="utf-8").write(content)
print("extracted chars:", len(content))
