import sys
import os
import re
import vlc

from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QSize, QTimer
from PyQt5.QtGui import QIcon, QPixmap

from ui_playlist import Ui_MainWindow

folder_path = "D://StreamripDownloads/Sveeee"

class MainWindow(QMainWindow):
    def __init__(self):
        self.current_song = None
        self.paused = None
        self.player = None
        self.seeking = False

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

        # Create a timer for the song slider
        self.progress_timer = QTimer()
        self.progress_timer.setInterval(500)  # Update every 0.5 seconds
        self.progress_timer.timeout.connect(self.update_progress_slider)

        self.ui.tableView.doubleClicked.connect(self.play_selected_song)
        self.ui.pushButton_playpause.pressed.connect(self.playpause)
        self.ui.horizontalSlider.sliderPressed.connect(self.begin_seek_from_slider)
        self.ui.horizontalSlider.valueChanged.connect(self.seek_from_slider)

 
    def play_selected_song(self, index):
        row = index.row()
        self.current_song = self.model.songs[row]
        file_path = self.current_song["file_path"]

        if self.player == None:
            self.player = vlc.MediaPlayer()

        # Stop current song if one is playing
        if self.player.is_playing():
            self.player.stop()

        self.player.set_media(vlc.Media(file_path))
        self.player.play()

        paused = False

        self.ui.pushButton_playpause.setEnabled(True)
        self.update_current_playing_ui()
    
    def update_current_playing_ui(self):
        if self.current_song != None:
            self.ui.pushButton_playpause.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
            self.ui.pushButton_next.setEnabled(True)

            self.ui.label_current_playing_title.setText(self.current_song["title"])
            self.ui.label_current_playing_artist.setText(self.current_song["artist"])

            if self.paused:
                self.progress_timer.stop()
                self.ui.pushButton_playpause.setText("Play")
            else:
                self.progress_timer.start()
                self.ui.pushButton_playpause.setText("Pause")

    def playpause(self):
        self.paused = not self.paused

        self.player.pause()

        self.update_current_playing_ui()

    def update_progress_slider(self):
        if(self.seeking):
            return

        if not self.paused:
            length = self.player.get_length()  # in ms
            pos = self.player.get_time()      # in ms

        if length > 0:
            value = int((pos / length) * self.ui.horizontalSlider.maximum())
            self.ui.horizontalSlider.blockSignals(True)  # Prevent recursive seek
            self.ui.horizontalSlider.setValue(value)
            self.ui.horizontalSlider.blockSignals(False)

    def begin_seek_from_slider(self):
        self.seeking = True

    def seek_from_slider(self):
        slider_value = self.ui.horizontalSlider.value()
        
        if self.player:
            length = self.player.get_length()
            print(slider_value)
            new_time = int((slider_value / self.ui.horizontalSlider.maximum()) * length)
            self.player.set_time(new_time)
            print("set time to " + str(new_time))

        self.seeking = False



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