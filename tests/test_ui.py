import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from bili_notes.qt_compat import QApplication

from bili_notes.core import Result, Store
from bili_notes.ui import THEME, Window


class Credentials:
    def get(self):
        return ""


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setStyle("Fusion")
    instance.setStyleSheet(THEME)
    return instance


def test_window_empty_validation_history_and_copy(app, tmp_path):
    store = Store(tmp_path)
    result = Result(
        "test",
        "测试视频",
        "BV1xx411c7mD",
        "gemini-test",
        "auto",
        "2026-09-07",
        "## 要点\n\n- 示例事实",
        "原始字幕",
        "字幕",
    )
    store.save(result)
    window = Window(store, Credentials())
    window.show()
    app.processEvents()
    assert window.history.count() == 1
    assert not window.copy_button.isEnabled()
    window.start_job()
    assert window.job is None
    window.open_history(window.history.item(0))
    assert "示例事实" in window.summary.toPlainText()
    assert window.transcript.toPlainText() == "原始字幕"
    window.copy()
    assert "示例事实" in app.clipboard().text()
    window.new_note()
    assert window.result is None
    window.close()
