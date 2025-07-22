import sys
import os
import re
import vlc
import random

from PyQt5.QtWidgets import QApplication, QMainWindow, QStyledItemDelegate, QStyleOptionButton, QStyle
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QSize, QTimer, pyqtSignal, QStringListModel, QSortFilterProxyModel, QThread
from PyQt5.QtGui import QIcon, QPainter, QPainterPath, QPixmap

from ui_playlist import Ui_MainWindow

from song_queue import SongQueue
from metadata_loader import MetadataLoader

folder_path = "D://StreamripDownloads/Sveeee"

class MainWindow(QMainWindow):
    def __init__(self):
        self.current_song = None
        self.paused = None
        self.player = None
        self.seeking = False
        self.song_queue = SongQueue()

        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

        super().__init__()

        with open("modern_style.qss", "r") as f:
            self.setStyleSheet(f.read())

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

        # Setup the table model
        self.model = MusicTableModel([])
        self.proxy_model = CustomSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        self.ui.tableView.setModel(self.proxy_model)
        self.ui.tableView.setIconSize(QSize(40, 40))

        self.ui.tableView.setColumnWidth(0, 30)   # Track number
        self.ui.tableView.setColumnWidth(1, 50)   # Cover
        self.ui.tableView.setColumnWidth(2, 350)  # Title
        self.ui.tableView.setColumnWidth(3, 300)  # Artist
        self.ui.tableView.setColumnWidth(4, 40)   # Queue button
        self.ui.tableView.setTextElideMode(Qt.ElideRight)
        self.ui.tableView.setSortingEnabled(True)
        self.ui.tableView.sortByColumn(0, Qt.AscendingOrder)
        self.ui.tableView.verticalHeader().setDefaultSectionSize(50)  # or any height you want

        # Start the background thread to load metadata
        self.load_metadata_in_background()

        # Create a timer for the song slider
        self.progress_timer = QTimer()
        self.progress_timer.setInterval(500)  # Update every 0.5 seconds
        self.progress_timer.timeout.connect(self.update_progress_slider)

        # Add "Add to queue" button to table
        delegate = ButtonDelegate()
        self.ui.tableView.setItemDelegateForColumn(4, delegate)
        delegate.clicked.connect(self.handle_add_to_queue_click)

        #self.ui.queue_panel.hide()
        self.queue_model = QStringListModel()
        self.ui.listView_queue.setModel(self.queue_model)

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.ui.widget_title_bar.setStyleSheet("""
            QWidget {
                background-color: #181818;
            }
        """)
        self.ui.toolButton_close_app.setStyleSheet("""
            QWidget {
                background-color: rgb(230, 48, 48);
            }
        """)

        self.ui.tableView.doubleClicked.connect(self.play_selected_song)
        self.ui.pushButton_playpause.pressed.connect(self.playpause)
        self.ui.horizontalSlider.sliderPressed.connect(self.begin_seek_from_slider)
        self.ui.horizontalSlider.valueChanged.connect(self.seek_from_slider)
        self.ui.pushButton_next.pressed.connect(self.play_next_song)
        self.ui.pushButton_previous.pressed.connect(self.play_previous_song)
        self.ui.pushButton_view_queue.pressed.connect(self.toggle_queue_panel)
        self.ui.toolButton_queue_panel_close.pressed.connect(self.toggle_queue_panel)
        self.ui.lineEdit_search.textChanged.connect(self.proxy_model.setFilterFixedString)
        self.ui.toolButton_close_app.pressed.connect(self.close_app)
        self.ui.toolButton_minimise_app.pressed.connect(self.minimise_app)

        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_song_end)

    def play_selected_song(self, proxy_index):
        row = self.proxy_model.mapToSource(proxy_index).row()
        self.current_song = self.model.songs[row]
        file_path = self.current_song["file_path"]

        self.song_queue.add_song_current(self.current_song)

        # Stop current song if one is playing
        if self.player.is_playing():
            self.player.stop()

        self.player.set_media(self.instance.media_new(file_path))
        self.player.play()

        paused = False

        self.ui.pushButton_playpause.setEnabled(True)
        self.update_current_playing_ui()
        self.update_queue_ui()
    
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
            length = self.player.get_length()
            pos = self.player.get_time()

        if length > 0:
            value = int((pos / length) * self.ui.horizontalSlider.maximum())
            self.ui.horizontalSlider.blockSignals(True)  # Prevent recursive seek
            self.ui.horizontalSlider.setValue(value)
            self.ui.horizontalSlider.blockSignals(False)

    def begin_seek_from_slider(self):
        self.seeking = True

    def seek_from_slider(self):        
        slider_value = self.ui.horizontalSlider.value()
        length = self.player.get_length()
        new_time = int((slider_value / self.ui.horizontalSlider.maximum()) * length)
        self.player.set_time(new_time)

        self.seeking = False

    def play_next_song(self, event = None):
        next_song = self.song_queue.get_next_song()

        if(next_song == None):
            next_song = random.choice(self.model.songs)
            # Adds the random song if nothing is next in queue and moves current index to it
            self.song_queue.add_song(next_song)
            self.song_queue.get_next_song()

        self.current_song = next_song
        if self.player.is_playing():
            self.player.stop()

        self.player.set_media(self.instance.media_new(self.current_song["file_path"]))
        self.player.play()

        self.paused = False

        self.update_current_playing_ui()
        self.update_queue_ui()

    def play_previous_song(self):
        previous_song = self.song_queue.get_previous_song()
        self.current_song = previous_song

        if self.player.is_playing():
            self.player.stop()

        self.player.set_media(self.instance.media_new(previous_song["file_path"]))
        self.player.play()

        self.paused = False

        self.update_current_playing_ui()
        self.update_queue_ui()

    def on_song_end(self, event):
        QTimer.singleShot(0, self.play_next_song)

    def handle_add_to_queue_click(self, proxy_index):
        row = self.proxy_model.mapToSource(proxy_index).row()
        self.song_queue.add_song(self.model.songs[row])

        if(len(self.song_queue.queue) == 1):
            self.play_next_song()

        self.update_queue_ui()

    def toggle_queue_panel(self):
        if self.ui.queue_panel.isVisible():
            self.ui.queue_panel.hide()
        else:
            self.ui.queue_panel.show()

    def update_queue_ui(self):
        self.queue_model.setStringList([(song["title"] + " - " + song["artist"]) for song in self.song_queue.queue])
        index = self.queue_model.index(self.song_queue.current_index)

        if index.isValid():
            self.ui.listView_queue.setCurrentIndex(index)

    # Handle title bar actions
    def mousePressEvent(self, event):
        if self.ui.widget_title_bar.underMouse():
            self._drag_active = True
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_active", False):
            self.move(event.globalPos() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_active = False

    def minimise_app(self):
        self.showMinimized()

    def close_app(self):
        self.close()

    def load_metadata_in_background(self):
        files = [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
        ]

        self.thread = QThread()
        self.worker = MetadataLoader(files, folder_path)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.song_loaded.connect(self.add_song_to_model)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.start()

    def add_song_to_model(self, song):
        self.model.beginInsertRows(QModelIndex(), len(self.model.songs), len(self.model.songs))
        self.model.songs.append(song)
        self.model.endInsertRows()
        self.ui.label_track_count.setText(f"{len(self.model.songs)} tracks")

class MusicTableModel(QAbstractTableModel):
    def __init__(self, songs):
        super().__init__()
        self.songs = songs

    def rowCount(self, parent=QModelIndex()):
        return len(self.songs)

    def columnCount(self, parent=QModelIndex()):
        return 5  # #, Cover, Title, Artist, Add to queue button

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
            elif col == 4:
                return ""

        elif role == Qt.DecorationRole and col == 1:
            pixmap = song["cover"].scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            rounded = self.rounded_pixmap(pixmap)
            return QIcon(rounded)

        return None

    def headerData(self, section, orientation, role):
        headers = ["#", "Cover", "Title", "Artist", ""]
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return headers[section]
        
    def rounded_pixmap(self, pixmap, radius=5):
        size = pixmap.size()
        rounded = QPixmap(size)
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size.width(), size.height(), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        return rounded
        
class ButtonDelegate(QStyledItemDelegate):
    clicked = pyqtSignal(QModelIndex)  # Emits the row/column of the button clicked

    def paint(self, painter, option, index):
        button = QStyleOptionButton()
        button.rect = option.rect
        button.text = "Q"
        button.state = QStyle.State_Enabled

        QApplication.style().drawControl(QStyle.CE_PushButton, button, painter)

    def editorEvent(self, event, model, option, index):
        if event.type() == event.MouseButtonRelease and option.rect.contains(event.pos()):
            self.clicked.emit(index)
            return True
        return False
    
class CustomSortFilterProxyModel(QSortFilterProxyModel):
    def lessThan(self, left, right):
        column = left.column()

        left_data = self.sourceModel().data(left, Qt.DisplayRole)
        right_data = self.sourceModel().data(right, Qt.DisplayRole)

        if column == 0:  # Track number column
            try:
                return int(left_data) < int(right_data)
            except ValueError:
                return False

        return super().lessThan(left, right)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())