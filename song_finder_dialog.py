from PyQt5.QtWidgets import QDialog
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QPixmap
from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal, QByteArray

from ui_add_song import Ui_SongFinderDialog

import os
import io
import re
import yt_dlp

import requests
import eyed3

from PIL import Image, ImageChops
from mutagen.id3 import ID3, APIC
from urllib.parse import quote, urlparse, parse_qs

folder_path = "/home/lonskyne/Music/Sveeee"
tmp_folder = "./tmp"

YOUTUBE_THUMBNAIL_SIZES = [
    "maxresdefault.jpg",
    "sddefault.jpg",
    "hqdefault.jpg",
    "mqdefault.jpg",
]

class SongFinderDialog(QDialog, Ui_SongFinderDialog):
    def __init__(self, parent):
        super().__init__()
        self.ui = Ui_SongFinderDialog()
        self.ui.setupUi(self)

        self.parent = parent
        self.model = QStandardItemModel()
        self.ui.label_warning.setText("")

        self.ui.pushButton_search.pressed.connect(self.search)
        self.ui.pushButton_download.pressed.connect(self.download_and_add_song)

    def search(self):
        self.clear_ui()

        results = self.youtube_search(self.ui.lineEdit_search.text())

        for title, url in results:
            print(title)
            item = QStandardItem(title)       # what the user sees
            item.setData(url, Qt.UserRole)    # store link hidden
            self.model.appendRow(item)

        self.ui.listView.setModel(self.model)

    def youtube_search(self, query, max_results=5):
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": "in_playlist",  # don't download, just list results
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # "ytsearch" works like typing into YouTube search bar
            search_url = f"ytsearch{max_results}:{query}"
            info = ydl.extract_info(search_url, download=False)
            return [(e["title"], e["url"]) for e in info["entries"]]

    def download_and_add_song(self):
        selected_indexes = self.ui.listView.selectedIndexes()

        if not selected_indexes:
            self.ui.label_warning.setText("You must select a song from the list")
            return
        if not self.ui.lineEdit_title.text():
            self.ui.label_warning.setText("You must enter the title of the track")
            return
        if not self.ui.lineEdit_artist.text():
            self.ui.label_warning.setText("You must enter the artist of the track")
            return

        self.ui.label_warning.setText("Downloading...")

        title = self.ui.lineEdit_title.text()
        artist = self.ui.lineEdit_artist.text()

        index = selected_indexes[0]
        item = self.model.itemFromIndex(index)
        url = item.data(Qt.UserRole)

        # Run in background thread
        self.thread = QThread()
        self.worker = DownloadWorker(url, tmp_folder)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(lambda file_path: self.on_download_finished(file_path, title, artist, url))
        self.worker.error.connect(self.on_download_error)

        # Cleanup
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.error.connect(self.thread.quit)

        self.thread.start()

    def on_download_finished(self, file_path, title, artist, video_url):
        self.ui.label_warning.setText("Fetching album art...")
        self.embed_art(file_path, title, artist, video_url)
        # Rename it to correct syntax
        track_number = self.get_next_track_number()

        new_file_name = str(track_number) + ". " + artist + " - " + title + ".mp3"
        tmp_file_path = os.path.join(tmp_folder, new_file_name)

        os.rename(file_path, tmp_file_path)

        # Move to music folder
        new_file_path = os.path.join(folder_path, new_file_name)
        os.rename(tmp_file_path, new_file_path)

        pixmap = QPixmap()

        extracted_mp3_img = self.extract_mp3_image(new_file_path)

        if extracted_mp3_img is not None:
            pixmap.loadFromData(QByteArray(self.extract_mp3_image(new_file_path)))

        new_song = {"track": track_number,
                    "title": title,
                    "artist": artist,
                    "cover": pixmap,
                    "file_path": new_file_path}

        self.parent.add_song_to_model(new_song)

        self.clear_ui(True)

        self.accept()

    def extract_mp3_image(self, file_path):
        try:
            audio = ID3(file_path)
            for tag in audio.values():
                if isinstance(tag, APIC):  # APIC = Attached Picture
                    return tag.data
        except:
            pass

        return None

    def on_download_error(self, message):
        self.ui.label_warning.setText(f"Download failed: {message}")
        self.reject()

    def get_next_track_number(self) -> int:
        track_numbers = []

        pattern = re.compile(r"^(\d+)\.\s")

        for filename in os.listdir(folder_path):
            match = pattern.match(filename)
            if match:
                num = int(match.group(1))
                track_numbers.append(num)

        if not track_numbers:
            return 1

        return max(track_numbers) + 1

    def embed_art(self, file_path, title, artist, video_url):
        ext = file_path.lower()

        image_data = self.download_album_art(artist, title, video_url)

        if not image_data:
            print("No album art found.")
            return

        success = False
        if ext.endswith(".mp3"):
            success = self.embed_album_art_mp3(file_path, image_data)
        else:
            print("Unsupported file format.")

        if success:
            self.ui.label_warning.setText("Album art embedded.")
        else:
            self.ui.label_warning.setText("Album art embedding failed.")

    def is_valid_youtube_thumbnail(self, response):
        """
        Detect YouTube placeholder thumbnails.
        """
        if response.status_code != 200:
            return False

        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type:
            return False

        # Placeholder images are usually tiny
        if len(response.content) < 2000:
            return False

        return True


    def extract_video_id(self, video_url):
        parsed = urlparse(video_url)

        if parsed.hostname in ["youtu.be"]:
            return parsed.path[1:]

        if parsed.hostname and "youtube.com" in parsed.hostname:
            return parse_qs(parsed.query).get("v", [None])[0]

        return None


    def download_album_art(self, artist, album, video_url):
        artist = artist.strip()
        album = album.strip()

        # Try iTunes Search API
        try:
            url = (
                f"https://itunes.apple.com/search?"
                f"term={quote(artist + ' ' + album)}"
                f"&media=music&entity=album&limit=1"
            )

            r = requests.get(url, timeout=10)
            r.raise_for_status()

            results = r.json().get("results", [])

            if results:
                artwork_url = results[0].get("artworkUrl100")

                if artwork_url:
                    artwork_url = artwork_url.replace(
                        "100x100bb.jpg",
                        "600x600bb.jpg"
                    )

                    img = requests.get(artwork_url, timeout=10)

                    if img.status_code == 200:
                        return img.content

        except Exception as e:
            print(f"[iTunes failed] {artist} - {album}: {e}")

        # Fallback: MusicBrainz + CoverArtArchive
        try:
            mb_search = (
                "https://musicbrainz.org/ws/2/release-group/"
                f"?query=artist:{quote(artist)}%20AND%20release:{quote(album)}"
                "&fmt=json"
            )

            r = requests.get(
                mb_search,
                headers={"User-Agent": "AlbumArtFetcher/1.0"},
                timeout=10
            )

            r.raise_for_status()

            results = r.json().get("release-groups", [])

            if results:
                release_group_id = results[0]["id"]

                cover_url = (
                    f"https://coverartarchive.org/"
                    f"release-group/{release_group_id}/front-500.jpg"
                )

                img = requests.get(cover_url, timeout=10)

                if img.status_code == 200:
                    return img.content

        except Exception as e:
            print(f"[MusicBrainz failed] {artist} - {album}: {e}")

        # Final fallback: YouTube thumbnail
        try:
            video_id = self.extract_video_id(video_url)

            if video_id:
                for size in YOUTUBE_THUMBNAIL_SIZES:
                    thumbnail_url = (
                        f"https://img.youtube.com/vi/"
                        f"{video_id}/{size}"
                    )

                    img = requests.get(thumbnail_url, timeout=10)

                    if self.is_valid_youtube_thumbnail(img):
                        return self.crop_to_square(img.content)

        except Exception as e:
            print(f"[YouTube failed] {artist} - {album}: {e}")

        return None

    def embed_album_art_mp3(self, mp3_path, image_data):
        try:
            audio = eyed3.load(mp3_path)
            if not audio:
                return False
            if not audio.tag:
                audio.initTag()
            audio.tag.images.set(3, image_data, "image/jpeg", u"Album Art")
            audio.tag.save()
            return True
        except Exception:
            return False

    def clear_ui(self, clear_search=False):
        if clear_search:
            self.ui.lineEdit_search.setText("")
        self.ui.lineEdit_artist.setText("")
        self.ui.lineEdit_title.setText("")

        self.ui.label_warning.setText("")

        self.model.clear()

    def crop_to_square(self, image_data):
        image = Image.open(io.BytesIO(image_data))

        # Remove black bars
        bg = Image.new(image.mode, image.size, (0, 0, 0))
        diff = ImageChops.difference(image, bg)
        bbox = diff.getbbox()
        if bbox:
            image = image.crop(bbox)

        width, height = image.size

        min_dim = min(width, height)
        print(f"width: {width}, height: {height}, mindim: {min_dim}")
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        right = left + min_dim
        bottom = top + min_dim
        print(f"{left}, {right}, {top}, {bottom}")

        cropped_image = image.crop((left, top, right, bottom))

        output = io.BytesIO()
        cropped_image.save(output, format='JPEG')
        return output.getvalue()


class DownloadWorker(QObject):
    finished = pyqtSignal(str)   # emits the downloaded file path
    error = pyqtSignal(str)      # emits error message if something goes wrong

    def __init__(self, url: str, output_dir: str = tmp_folder):
        super().__init__()
        self.url = url
        self.output_dir = output_dir

    def run(self):
        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{self.output_dir}/%(title)s.%(ext)s",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "quiet": False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                filename = ydl.prepare_filename(info)
                mp3_file = filename.rsplit(".", 1)[0] + ".mp3"

            self.finished.emit(mp3_file)
        except Exception as e:
            self.error.emit(str(e))
