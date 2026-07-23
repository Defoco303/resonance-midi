from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

import config_store
from qt_app import ResonanceMidiWindow


class PlaylistScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_config_path = config_store.CONFIG_PATH
        config_store.CONFIG_PATH = Path(self.temp_dir.name) / "config.json"
        self.window = ResonanceMidiWindow()

    def tearDown(self) -> None:
        if self.window.playlist_window is not None:
            self.window.playlist_window.close()
        self.window.close()
        QApplication.processEvents()
        config_store.CONFIG_PATH = self.old_config_path
        self.temp_dir.cleanup()

    def test_open_playlist_outer_size_tracks_ui_scale(self) -> None:
        self.window.open_playlist()
        playlist = self.window.playlist_window
        self.assertIsNotNone(playlist)
        playlist.resize(800, 400)

        self.window.set_ui_scale(1.5)

        self.assertEqual((playlist.width(), playlist.height()), (1200, 600))
        self.assertEqual(
            (playlist.minimumWidth(), playlist.minimumHeight()),
            (645, 285),
        )

    def test_closed_playlist_geometry_tracks_ui_scale(self) -> None:
        self.window._playlist_geometry = QRect(40, 50, 800, 400)

        self.window.set_ui_scale(0.5)

        self.assertEqual(self.window._playlist_geometry, QRect(40, 50, 400, 200))

    def test_repeated_scale_changes_use_ratio_not_compounded_base_metrics(self) -> None:
        self.window.open_playlist()
        playlist = self.window.playlist_window
        self.assertIsNotNone(playlist)
        playlist.resize(800, 400)

        self.window.set_ui_scale(2.0)
        self.window.set_ui_scale(1.0)

        self.assertEqual((playlist.width(), playlist.height()), (800, 400))


if __name__ == "__main__":
    unittest.main()
