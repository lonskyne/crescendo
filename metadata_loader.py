
import os
import re

from mutagen.flac import FLAC

from PyQt5.QtCore import pyqtSignal, QByteArray, QThread
from PyQt5.QtGui import QPixmap

class MetadataLoader(QThread):
    finished = pyqtSignal()
    song_loaded = pyqtSignal(dict)

    def __init__(self, song_files, folder_path):
        super().__init__()
        self.song_files = song_files
        self.folder_path = folder_path

    def run(self):
        for file in self.song_files:
            match = re.match(r"(\d+)\.\s*(.+?)\s*-\s*(.+?)(?:\s*\(.*\))?\.flac", file)
            if match:
                track_num = int(match.group(1))
                artist = match.group(2).strip()
                title = match.group(3).strip()

                song = {
                    "track": track_num,
                    "title": title,
                    "artist": artist,
                    "cover": self.get_album_art_pixmap(os.path.join(self.folder_path, file)),
                    "file_path": os.path.join(self.folder_path, file)
                }
                self.song_loaded.emit(song)
        self.finished.emit()

    def extract_flac_image(self, file_path):
        audio = FLAC(file_path)
        if audio.pictures:
            picture = audio.pictures[0]
            return picture.data
        return None

    def get_album_art_pixmap(self, file_path):
        data = self.extract_flac_image(file_path)
        if not data:
            data = self.extract_flac_image(self.folder_path + "/artworks/default.jpg")

        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(data))
        return pixmap