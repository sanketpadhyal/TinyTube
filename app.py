import os, uuid, shutil, re
from flask import Flask, render_template, request, send_file, after_this_request
from yt_dlp import YoutubeDL

app = Flask(__name__)

BASE_DIR   = os.path.abspath(os.path.dirname(__file__))
DOWNLOADS  = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOADS, exist_ok=True)

# ───────────────────────── helpers ──────────────────────────
def human(bytes_):
    if not bytes_:
        return "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} PB"

def normalize(url):
    url = url.strip()
    m = re.match(r"https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    if "youtube.com/shorts/" in url:
        vid = url.split("/shorts/")[1].split("?")[0].split("/")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    return url

def get_video_id(url):
    return normalize(url).split("watch?v=")[-1][:11]

def probe(url):
    with YoutubeDL({"skip_download": True, "quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    vids, auds = [], []
    for f in info["formats"]:
        ext  = f["ext"]
        size = f.get("filesize") or f.get("filesize_approx") or 0
        w, h = f.get("width"), f.get("height") or 0

        if f.get("vcodec") != "none" and f.get("acodec") != "none":
            vids.append({
                "fmt": f["format_id"],
                "res_label": f"{h}p" if h else "—",
                "res_full":  f"{w}x{h}" if w and h else "—",
                "height": h,
                "size": human(size),
                "ext": ext,
            })

        if f.get("vcodec") == "none" and f.get("acodec") != "none":
            abr = f.get("abr")
            if abr:
                auds.append({
                    "fmt": f["format_id"],
                    "abr": f"{abr:.0f} kbps",
                    "size": human(size),
                    "ext": ext,
                })

    vids.sort(key=lambda x: x["height"], reverse=True)
    auds.sort(key=lambda x: float(x["abr"].split()[0]), reverse=True)
    return info["title"], vids, auds

def yt_download(url, fmt, out_dir):
    """
    Download selected format and return the *actual* file path.
    Falls back to 'most recent file in folder' if prepare_filename() is stale.
    """
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, "%(title).80s.%(ext)s")

    opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "quiet": True,
        "merge_output_format": "mkv",
    }

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        expected = ydl.prepare_filename(info)

    # if yt‑dlp post‑processed the file, 'expected' may not exist.
    if os.path.exists(expected):
        return expected

    # fallback: newest file in the folder
    files = sorted(
        [os.path.join(out_dir, f) for f in os.listdir(out_dir)],
        key=os.path.getmtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("Download finished but no file found.")
    return files[0]

# ───────────────────────── routes ───────────────────────────
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/search")
def search():
    return render_template("search.html")

@app.route("/choose", methods=["POST"])
def choose():
    url = normalize(request.form["url"])
    try:
        title, vids, auds = probe(url)
    except Exception as e:
        return f"<h3>Error</h3><pre>{e}</pre>"
    return render_template(
        "choose.html",
        url=url,
        title=title,
        videos=vids,
        audios=auds,
        thumb_id=get_video_id(url),
    )

@app.route("/download", methods=["POST"])
def download():
    url = normalize(request.form["url"])
    fmt = request.form["format_id"]

    temp_dir = os.path.join(DOWNLOADS, uuid.uuid4().hex)
    try:
        file_path = yt_download(url, fmt, temp_dir)
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return f"<h3>Download failed</h3><pre>{e}</pre>"

    @after_this_request
    def cleanup(resp):
        shutil.rmtree(temp_dir, ignore_errors=True)
        return resp

    return send_file(file_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
