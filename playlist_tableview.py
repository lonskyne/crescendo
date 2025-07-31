from PyQt5.QtWidgets import QApplication, QStyledItemDelegate, QStyleOptionButton, QStyle
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, pyqtSignal, QSortFilterProxyModel
from PyQt5.QtGui import QIcon, QPainter, QPainterPath, QPixmap


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
            if song["cover"] is None:
                return QIcon()

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
