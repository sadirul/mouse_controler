"""Activity log page: every gesture-triggered action with its result."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableView, QVBoxLayout, QWidget

from app.logger import ActivityEntry, ActivityLog
from ui import theme
from ui.widgets import page_header

COLUMNS = ["Time", "Gesture", "Action", "Result", "Error details"]


class _Bridge(QObject):
    """ActivityLog listeners run on the tracking thread; this re-emits on the GUI thread."""

    entry = Signal(object)


class ActivityModel(QAbstractTableModel):
    def __init__(self, entries: list[ActivityEntry]):
        super().__init__()
        self.all = list(entries)
        self.errors_only = False
        self.rows = self.all

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        e = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return [e.time_text, e.gesture, e.action, "Success" if e.success else "Failed", e.error][col]
        if role == Qt.ItemDataRole.ForegroundRole and col == 3:
            return QColor(theme.OK if e.success else theme.DANGER)
        if role == Qt.ItemDataRole.ToolTipRole and e.error:
            return e.error
        return None

    def add(self, entry: ActivityEntry) -> None:
        visible = not self.errors_only or not entry.success
        if visible:
            row = len(self.rows)
            self.beginInsertRows(QModelIndex(), row, row)
        self.all.append(entry)
        if visible and self.errors_only:
            self.rows.append(entry)
        if visible:
            self.endInsertRows()
        if len(self.all) > 5000:  # keep the table light during long sessions
            self.beginResetModel()
            self.all = self.all[-4000:]
            self._refilter()
            self.endResetModel()

    def _refilter(self) -> None:
        self.rows = [e for e in self.all if not e.success] if self.errors_only else self.all

    def set_errors_only(self, on: bool) -> None:
        self.beginResetModel()
        self.errors_only = on
        self._refilter()
        self.endResetModel()

    def clear(self) -> None:
        self.beginResetModel()
        self.all = []
        self._refilter()
        self.endResetModel()


class ActivityLogsPage(QWidget):
    def __init__(self, activity: ActivityLog, parent=None):
        super().__init__(parent)
        self.activity = activity
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(12)
        lay.addWidget(page_header("Activity logs", "Every gesture that triggered an action, and whether the action "
                                                   "succeeded. Full technical logs are written to logs/app.log."))
        bar = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItems(["All entries", "Failures only"])
        self.filter.currentIndexChanged.connect(lambda i: self.model.set_errors_only(i == 1))
        self.count = QLabel()
        self.count.setObjectName("Muted")
        clear = QPushButton("Clear logs")
        clear.clicked.connect(self.clear)
        bar.addWidget(self.filter)
        bar.addWidget(self.count, 1)
        bar.addWidget(clear)
        lay.addLayout(bar)

        self.model = ActivityModel(activity.entries())
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 200)
        lay.addWidget(self.table, 1)

        self._bridge = _Bridge()
        self._bridge.entry.connect(self._add)
        activity.add_listener(self._bridge.entry.emit)
        self._update_count()

    def _add(self, entry: ActivityEntry) -> None:
        at_bottom = self.table.verticalScrollBar().value() >= self.table.verticalScrollBar().maximum() - 4
        self.model.add(entry)
        if at_bottom:
            self.table.scrollToBottom()
        self._update_count()

    def _update_count(self) -> None:
        failures = sum(1 for e in self.model.all if not e.success)
        self.count.setText(f"   {len(self.model.all)} entries, {failures} failure(s)")

    def clear(self) -> None:
        self.activity.clear()
        self.model.clear()
        self._update_count()
