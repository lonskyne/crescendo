import sys
import os
import re
import vlc

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QSize
from PyQt5.QtGui import QIcon, QPixmap

from ui_playlist import Ui_MainWindow

folder_path = "D://StreamripDownloads/Sveeee"

class MainWindow(QMainWindow):
    def __init__(self):
        self.player = None

        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Set playlist name
        self.ui.label_playlist_name.setText(os.path.basename(folder_path))

        # Set track count
        song_count = 0
        for path in os.listdir(folder_path):
            if os.path.isfile(os.path.join(folder_path, path)):
                song_count += 1

        self.ui.label_track_count.setText(str(song_count) + " tracks")

        # Populate song list
        files = [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
        ]

        songs = []

        for file in files:
            match = re.match(r"(\d+)\.\s*(.+?)\s*-\s*(.+?)(?:\s*\(.*\))?\.flac", file)
            if match:
                track_num = int(match.group(1))
                artist = match.group(2).strip()
                title = match.group(3).strip()

                song = {
                    "track": track_num,
                    "title": title,
                    "artist": artist,
                    "cover": folder_path + "/__artwork/default.jpg",
                    "file_path": os.path.join(folder_path, file)
                }
                songs.append(song)

        # Sort by track number
        songs.sort(key=lambda x: x["track"])

        self.model = MusicTableModel(songs)
        self.ui.tableView.setModel(self.model)
        self.ui.tableView.resizeColumnsToContents()
        self.ui.tableView.setIconSize(QSize(30, 30))


        self.ui.tableView.doubleClicked.connect(self.play_selected_song)

 
    def play_selected_song(self, index):
        row = index.row()
        song = self.model.songs[row]
        file_path = song["file_path"]

        if self.player == None:
            self.player = vlc.MediaPlayer()

        # Stop current song if one is playing
        if self.player.is_playing():
            self.player.stop()

        self.player.set_media(vlc.Media(file_path))
        self.player.play()
            


class MusicTableModel(QAbstractTableModel):
    def __init__(self, songs):
        super().__init__()
        self.songs = songs

    def rowCount(self, parent=QModelIndex()):
        return len(self.songs)

    def columnCount(self, parent=QModelIndex()):
        return 4  # #, Cover, Title, Artist

    def data(self, index, role):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        song = self.songs[row]

        if role == Qt.DisplayRole:
            if col == 0:
                return str(song["track"])
            elif col == 2:
                return song["title"]
            elif col == 3:
                return song["artist"]

        elif role == Qt.DecorationRole and col == 1:
            pixmap = QPixmap(song["cover"]).scaled(40, 40, Qt.KeepAspectRatio)
            return QIcon(pixmap)

        return None

    def headerData(self, section, orientation, role):
        headers = ["#", "Cover", "Title", "Artist"]
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return headers[section]
        

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())