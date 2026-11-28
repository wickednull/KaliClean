#!/usr/bin/env python3
"""KaliClean - a frosted-glass system hygiene utility for Kali Linux."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

# Must be set before QApplication is created (required by QtWebEngine).
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --log-level=3"
)

from PySide6.QtCore import (  # noqa: E402
    QObject,
    QTimer,
    QUrl,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QGuiApplication, QIcon  # noqa: E402
from PySide6.QtWebChannel import QWebChannel  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from backend import Cleaner, TASKS, human, system_stats  # noqa: E402

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "web" / "index.html"
ICON = ROOT / "assets" / "kaliclean.png"


class GlassPage(QWebEnginePage):
    """A web page with a transparent background so rounded corners show through."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundColor(QColor(0, 0, 0, 0))


class Bridge(QObject):
    """The JS <-> Python API exposed to the UI as `window.bridge`."""

    tasksUpdated = Signal(str)
    statsUpdated = Signal(str)
    sizesUpdated = Signal(str)
    logEvent = Signal(str)
    progressEvent = Signal(str)
    authResult = Signal(bool, str)
    finishedEvent = Signal(str)

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window
        self.cleaner = Cleaner()
        self.running = False

    # -- information -------------------------------------------------------
    @Slot()
    def getTasks(self):
        self.tasksUpdated.emit(json.dumps(TASKS))

    @Slot()
    def refreshStats(self):
        self.statsUpdated.emit(json.dumps(system_stats()))

    @Slot()
    def refreshSizes(self):
        from backend import estimate

        sizes = {task["id"]: estimate(task["id"]) for task in TASKS}
        self.sizesUpdated.emit(json.dumps(sizes))

    @Slot(str)
    def verifyPassword(self, password: str):
        ok, message = self.cleaner.verify_password(password)
        self.authResult.emit(ok, message)

    # -- window controls ---------------------------------------------------
    @Slot(float, float)
    def drag(self, dx: float, dy: float):
        position = self.window.pos()
        self.window.move(position.x() + int(dx), position.y() + int(dy))

    @Slot()
    def minimize(self):
        self.window.showMinimized()

    @Slot()
    def maximize(self):
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    @Slot()
    def closeWin(self):
        self.window.close()

    # -- cleaning ----------------------------------------------------------
    @Slot(str, str)
    def startClean(self, task_ids_json: str, _password: str):
        if self.running:
            return
        try:
            task_ids = json.loads(task_ids_json)
        except (TypeError, ValueError):
            return
        if not isinstance(task_ids, list) or not task_ids:
            return
        self.running = True
        thread = threading.Thread(
            target=self._worker, args=(task_ids,), daemon=True, name="kaliclean-worker"
        )
        thread.start()

    def _emit_log(self, kind: str, message: str):
        self.logEvent.emit(
            json.dumps(
                {"time": time.strftime("%H:%M:%S"), "kind": kind, "message": message}
            )
        )

    def _worker(self, task_ids: list[str]):
        total = len(task_ids)
        started = time.time()
        results = []
        freed_total = 0

        self._emit_log("info", f"Starting {total} cleanup task{'s' if total != 1 else ''}…")

        for index, task_id in enumerate(task_ids, start=1):
            task = next((item for item in TASKS if item["id"] == task_id), None)
            label = task["name"] if task else task_id
            self.progressEvent.emit(
                json.dumps(
                    {
                        "current": index,
                        "total": total,
                        "percent": round((index - 1) / total * 100),
                        "label": label,
                    }
                )
            )
            self._emit_log("run", f"{label}…")
            result = self.cleaner.run_task(task_id)
            results.append({"id": task_id, "name": label, **result})
            freed_total += result.get("freed", 0)
            kind = "ok" if result.get("ok") else "warn"
            amount = human(result.get("freed", 0))
            self._emit_log(
                kind,
                f"{label}: {result.get('detail', 'done')}"
                + (f" · {amount}" if result.get("freed", 0) else ""),
            )

        self.progressEvent.emit(
            json.dumps(
                {
                    "current": total,
                    "total": total,
                    "percent": 100,
                    "label": "Complete",
                }
            )
        )
        self._emit_log("ok", f"Finished in {time.time() - started:.1f}s · {human(freed_total)} reclaimed")
        self.finishedEvent.emit(
            json.dumps(
                {
                    "freed": freed_total,
                    "duration": round(time.time() - started, 1),
                    "results": results,
                }
            )
        )
        self.statsUpdated.emit(json.dumps(system_stats()))
        self.refreshSizes()
        self.running = False


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(960, 780)
        self.resize(1180, 900)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = QWebEngineView()
        page = GlassPage(self.view)
        self.view.setPage(page)
        self.view.setStyleSheet("background: transparent;")
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        layout.addWidget(self.view)

        self.bridge = Bridge(self)
        channel = QWebChannel(self)
        channel.registerObject("bridge", self.bridge)
        page.setWebChannel(channel)

        self.view.loadFinished.connect(self._on_loaded)
        self.view.setUrl(QUrl.fromLocalFile(str(INDEX)))

    def _on_loaded(self, ok: bool):
        if ok:
            QTimer.singleShot(150, self.bridge.refreshStats)
            QTimer.singleShot(250, self.bridge.refreshSizes)

    def closeEvent(self, event):
        self.view.page().deleteLater()
        super().closeEvent(event)


def main():
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setApplicationName("KaliClean")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("com.github.wickednull.KaliClean.desktop")
    if ICON.is_file():
        icon = QIcon(str(ICON))
        app.setWindowIcon(icon)

    window = MainWindow()
    if ICON.is_file():
        window.setWindowIcon(QIcon(str(ICON)))
    screen = QGuiApplication.primaryScreen()
    if screen:
        geometry = screen.availableGeometry()
        window.move(
            geometry.x() + (geometry.width() - window.width()) // 2,
            geometry.y() + (geometry.height() - window.height()) // 2,
        )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
