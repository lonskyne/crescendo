from PyQt5.QtWidgets import QDialog
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal

from ui_add_song import Ui_SongFinderDialog

import os
import re
import yt_dlp

import requests
import eyed3
from urllib.parse import quote_plus, quote
from mutagen.id3 import ID3NoHeaderError



folder_path = "/home/lonskyne/Music/Sveeee"
tmp_folder = "./tmp"

class SongFinderDialog(QDialog, Ui_SongFinderDialog):
    def __init__(self):
        super().__init__()
        self.ui = Ui_SongFinderDialog()
        self.ui.setupUi(self)

        self.model = QStandardItemModel()
        self.ui.label_warning.setText("")

        self.ui.pushButton_search.pressed.connect(self.search)
        self.ui.pushButton_download.pressed.connect(self.download_and_add_song)

    def search(self):
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
            print(info["entries"])
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
        self.worker.finished.connect(lambda file_path: self.on_download_finished(file_path, title, artist))
        self.worker.error.connect(self.on_download_error)

        # Cleanup
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.error.connect(self.thread.quit)

        self.thread.start()

    def on_download_finished(self, file_path, title, artist):
        self.ui.label_warning.setText("Fetching album art...")
        self.embed_art(file_path, title, artist)
        # Rename it to correct syntax
        track_number = self.get_next_track_number()

        new_file_name = str(track_number) + ". " + artist + " - " + title + ".mp3"
        new_file_path = os.path.join(tmp_folder, new_file_name)

        os.rename(file_path, new_file_path)

        # Move to music folder
        os.rename(new_file_path, os.path.join(folder_path, new_file_name))

    def on_download_error(self, message):
        self.ui.label_warning.setText(f"Download failed: {message}")

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

    def embed_art(self, file_path, title, artist):
        ext = file_path.lower()

        image_data = self.download_album_art(artist, title)

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

    def download_album_art(self, artist, album):
        # Normalize inputs
        artist = artist.strip()
        album = album.strip()

        # Try iTunes Search API
        try:
            url = f"https://itunes.apple.com/search?term={quote(artist + ' ' + album)}&media=music&entity=album&limit=1"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                artwork_url = results[0].get("artworkUrl100")
                if artwork_url:
                    # Get higher resolution version
                    artwork_url = artwork_url.replace("100x100bb.jpg", "600x600bb.jpg")
                    img_data = requests.get(artwork_url, timeout=10).content
                    return img_data
        except Exception as e:
            print(f"[iTunes failed] {artist} - {album}: {e}")

        # Fallback: MusicBrainz
        try:
            # Search MusicBrainz Release Group
            mb_search = f"https://musicbrainz.org/ws/2/release-group/?query=artist:{quote(artist)}%20AND%20release:{quote(album)}&fmt=json"
            r = requests.get(mb_search, headers={"User-Agent": "AlbumArtFetcher/1.0"}, timeout=10)
            r.raise_for_status()
            results = r.json().get("release-groups", [])
            if results:
                release_group_id = results[0]["id"]
                cover_url = f"https://coverartarchive.org/release-group/{release_group_id}/front-500.jpg"
                img_data = requests.get(cover_url, timeout=10).content
                return img_data
        except Exception as e:
            print(f"[MusicBrainz failed] {artist} - {album}: {e}")

        return None

    def embed_album_art_mp3(self, mp3_path, image_data):
        """Embed album art into an MP3 file using eyeD3."""
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

