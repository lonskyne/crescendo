import os
import vlc
import random

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtCore import Qt, QModelIndex, QSize, QTimer, QStringListModel, QThread

from ui_playlist import Ui_MainWindow

from song_queue import SongQueue
from metadata_loader import MetadataLoader
from playlist_tableview import MusicTableModel, ButtonDelegate, CustomSortFilterProxyModel

folder_path = "/home/lonskyne/Music/Sveeee"

class MainWindow(QMainWindow):

    def __init__(self):
        self.current_song = None
        self.paused = None
        self.player = None
        self.seeking = False
        self.song_queue = SongQueue()
        self.shuffle = True

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
        self.ui.tableView.verticalHeader().setDefaultSectionSize(50)

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

        self.queue_model = QStringListModel()
        self.ui.listView_queue.setModel(self.queue_model)

        self.ui.tableView.doubleClicked.connect(self.play_selected_song)
        self.ui.pushButton_playpause.pressed.connect(self.playpause)
        self.ui.horizontalSlider.sliderPressed.connect(self.begin_seek_from_slider)
        self.ui.horizontalSlider.valueChanged.connect(self.seek_from_slider)
        self.ui.pushButton_next.pressed.connect(self.play_next_song)
        self.ui.pushButton_previous.pressed.connect(self.play_previous_song)
        self.ui.pushButton_view_queue.pressed.connect(self.toggle_queue_panel)
        self.ui.toolButton_queue_panel_close.pressed.connect(self.toggle_queue_panel)
        self.ui.lineEdit_search.textChanged.connect(self.proxy_model.setFilterFixedString)
        self.ui.pushButton_shuffle.pressed.connect(self.toggle_shuffle)

        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_song_end)

        self.ui.splitter.setSizes([int(self.width() * 0.75), int(self.width() * 0.25)])
        self.ui.queue_panel.hide()

    def play_selected_song(self, proxy_index):
        row = self.proxy_model.mapToSource(proxy_index).row()
        self.current_song = self.model.songs[row]
        file_path = self.current_song["file_path"]

        self.song_queue.add_song_current(self.current_song)

        if self.player.is_playing():
            self.player.stop()

        self.player.set_media(self.instance.media_new(file_path))
        self.player.play()

        self.paused = False

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
                self.ui.pushButton_playpause.setIcon(QIcon("./icons/play.png"))
            else:
                self.progress_timer.start()
                self.ui.pushButton_playpause.setIcon(QIcon("./icons/pause.png"))

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
            if(self.shuffle):
                # Adds the random song if nothing is next in queue and moves current index to it
                next_song = random.choice(self.model.songs)
            else:
                # Find current row by comparing song dicts in proxy model order
                for proxy_row in range(self.proxy_model.rowCount()):
                    # Map the proxy row to the source model row
                    source_index = self.proxy_model.mapToSource(self.proxy_model.index(proxy_row, 0))
                    source_row = source_index.row()
                    song = self.model.songs[source_row]

                    if song == self.current_song:
                        next_proxy_row = (proxy_row + 1) % self.proxy_model.rowCount()
                        next_source_index = self.proxy_model.mapToSource(self.proxy_model.index(next_proxy_row, 0))
                        next_song = self.model.songs[next_source_index.row()]
                        break

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

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
