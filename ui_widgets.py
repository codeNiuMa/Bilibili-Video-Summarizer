from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, Property, QPropertyAnimation, QRect, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QMouseEvent, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QComboBox, QFrame, QHBoxLayout, QLabel, QProxyStyle, QSizePolicy, QStyle, QTextEdit, QVBoxLayout, QWidget

SUPPORTED_MEDIA = (
    ".m4s", ".mp3", ".mp4", ".m4a", ".wav", ".aac", ".flac",
    ".ogg", ".webm", ".mkv", ".mov",
)

APP_FONT_FAMILY = "Microsoft YaHei UI"
APP_EMOJI_FAMILY = "Segoe UI Emoji"
APP_FONT_SIZE = 10

def _paint_icon(kind: str, color: str, size: int = 18) -> QPixmap:
    """Draw small Fluent-like line icons without relying on emoji/icon fonts."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    scale = size / 18.0
    painter.scale(scale, scale)

    if kind == "minimize":
        painter.drawLine(QPointF(4.2, 9.0), QPointF(13.8, 9.0))
    elif kind == "maximize":
        painter.drawRoundedRect(QRectF(4.2, 4.2, 9.6, 9.6), 0.7, 0.7)
    elif kind == "restore":
        painter.drawRoundedRect(QRectF(5.1, 6.0, 8.0, 7.2), 0.6, 0.6)
        painter.drawLine(QPointF(7.0, 4.6), QPointF(13.6, 4.6))
        painter.drawLine(QPointF(13.6, 4.6), QPointF(13.6, 11.0))
        painter.drawLine(QPointF(7.0, 4.6), QPointF(7.0, 5.9))
    elif kind == "close":
        painter.drawLine(QPointF(5.0, 5.0), QPointF(13.0, 13.0))
        painter.drawLine(QPointF(13.0, 5.0), QPointF(5.0, 13.0))
    elif kind == "refresh":
        painter.drawArc(QRectF(3.4, 3.4, 11.2, 11.2), 35 * 16, 285 * 16)
        painter.drawLine(QPointF(12.2, 3.9), QPointF(14.6, 3.7))
        painter.drawLine(QPointF(14.6, 3.7), QPointF(14.0, 6.1))
    elif kind == "sun":
        painter.drawEllipse(QRectF(6.0, 6.0, 6.0, 6.0))
        for a, b in [
            ((9, 2.5), (9, 4.2)), ((9, 13.8), (9, 15.5)),
            ((2.5, 9), (4.2, 9)), ((13.8, 9), (15.5, 9)),
            ((4.3, 4.3), (5.5, 5.5)), ((12.5, 12.5), (13.7, 13.7)),
            ((12.5, 5.5), (13.7, 4.3)), ((4.3, 13.7), (5.5, 12.5)),
        ]:
            painter.drawLine(QPointF(*a), QPointF(*b))
    elif kind == "moon":
        path = QPainterPath()
        path.moveTo(12.8, 3.5)
        path.cubicTo(8.3, 3.8, 6.0, 6.2, 6.0, 9.0)
        path.cubicTo(6.0, 12.1, 8.4, 14.2, 12.4, 14.4)
        path.cubicTo(10.8, 15.1, 9.4, 15.4, 8.0, 15.2)
        path.cubicTo(4.5, 14.8, 2.8, 12.1, 2.8, 9.0)
        path.cubicTo(2.8, 5.3, 5.6, 2.5, 9.4, 2.5)
        path.cubicTo(10.7, 2.5, 11.8, 2.9, 12.8, 3.5)
        painter.drawPath(path)
    elif kind == "key":
        painter.drawEllipse(QRectF(3.0, 4.7, 5.8, 5.8))
        painter.drawLine(QPointF(8.1, 9.3), QPointF(14.8, 14.0))
        painter.drawLine(QPointF(12.2, 12.2), QPointF(13.6, 10.8))
        painter.drawLine(QPointF(13.5, 13.1), QPointF(14.8, 11.8))
    elif kind == "cookie":
        painter.drawEllipse(QRectF(3.0, 3.0, 12.0, 12.0))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(6.0, 6.0, 1.6, 1.6))
        painter.drawEllipse(QRectF(10.4, 6.9, 1.5, 1.5))
        painter.drawEllipse(QRectF(8.0, 10.5, 1.5, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == "log":
        painter.drawRoundedRect(QRectF(4.0, 2.8, 10.0, 12.4), 1.1, 1.1)
        painter.drawLine(QPointF(6.2, 6.3), QPointF(11.8, 6.3))
        painter.drawLine(QPointF(6.2, 9.0), QPointF(11.8, 9.0))
        painter.drawLine(QPointF(6.2, 11.7), QPointF(10.0, 11.7))

    painter.end()
    return pixmap


def make_icon(kind: str, color: str, active_color: str | None = None, size: int = 18) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_paint_icon(kind, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(
        _paint_icon(kind, active_color or color, size),
        QIcon.Mode.Active,
        QIcon.State.Off,
    )
    return icon

class _ComboListPopupStyle(QProxyStyle):
    """Force QComboBox to use a list-view popup instead of menu-like scrollers.

    On Windows, SH_ComboBox_Popup can make Qt create the black
    QComboBoxPrivateScroller bars at the top and bottom of long popups.
    Returning 0 gives us a normal list popup with a standard vertical scrollbar.
    """

    def styleHint(
        self,
        hint,
        option=None,
        widget=None,
        returnData=None,
    ):  # noqa: N802
        if hint == QStyle.StyleHint.SH_ComboBox_Popup:
            return 0
        return super().styleHint(
            hint,
            option,
            widget,
            returnData,
        )


class SmartComboBox(QComboBox):
    """A non-editable combo box with a stable, bounded popup and custom chevron.

    Qt/Windows may turn long non-editable combo popups into menu-like lists
    with black auto-scroll strips at the top and bottom. This widget forces a
    normal list-view popup instead, caps its height, uses a standard vertical
    scrollbar, anchors it under the field whenever space permits, and draws
    its own chevron so the drop-down affordance is always visible.
    """

    def __init__(
        self,
        parent=None,
        *,
        max_visible_items: int = 9,
        max_popup_width: int = 460,
    ):
        super().__init__(parent)

        # Disable Qt's menu-style QComboBoxPrivateScroller strips. Keep the
        # style object alive on this combo for the lifetime of the widget.
        self._popup_style = _ComboListPopupStyle(self.style())
        self._popup_style.setParent(self)
        self.setStyle(self._popup_style)

        self._max_popup_items = max(3, int(max_visible_items))
        self._max_popup_width = max(220, int(max_popup_width))

        self.setEditable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaxVisibleItems(self._max_popup_items)

        view = self.view()
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)

        # Smooth item-by-item scrolling via wheel / side scrollbar only.
        # No top/bottom auto-scroll strips are used.
        view.setVerticalScrollMode(view.ScrollMode.ScrollPerPixel)

    def paintEvent(self, event) -> None:  # noqa: N802
        # Let Qt/QSS draw the normal combo first.
        super().paintEvent(event)

        # Then draw a small chevron ourselves. This avoids relying on the
        # platform's native combo arrow, which can disappear after QSS styling.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = self.palette().color(QPalette.ColorRole.Text)
        color.setAlpha(190)

        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = float(self.width() - 17)
        cy = float(self.height()) / 2.0 - 0.5
        painter.drawLine(QPointF(cx - 4.0, cy - 2.0), QPointF(cx, cy + 2.0))
        painter.drawLine(QPointF(cx, cy + 2.0), QPointF(cx + 4.0, cy - 2.0))
        painter.end()

    def showPopup(self) -> None:  # noqa: N802
        if self.count() <= 0:
            return

        super().showPopup()

        # Some styles resize/reposition the popup after showPopup() returns,
        # therefore position once now and once again on the next event-loop turn.
        self._position_popup()
        QTimer.singleShot(0, self._position_popup)

    def _position_popup(self) -> None:
        view = self.view()
        if view is None:
            return

        popup = view.window()
        if popup is None or popup is self.window():
            return

        screen = self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()

        # Use the real row height when available.
        row_height = view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = max(30, self.fontMetrics().height() + 12)

        visible_rows = min(max(1, self.count()), self._max_popup_items)
        desired_height = row_height * visible_rows + 6

        # Width: at least the field width, wide enough for normal model names,
        # but never absurdly wide on a small display.
        metrics = self.fontMetrics()
        longest = 0
        for i in range(self.count()):
            longest = max(longest, metrics.horizontalAdvance(self.itemText(i)))
        desired_width = max(self.width(), longest + 46)
        desired_width = min(
            desired_width,
            self._max_popup_width,
            max(self.width(), available.width() - 24),
        )

        field_top = self.mapToGlobal(QPoint(0, 0))
        field_bottom = self.mapToGlobal(QPoint(0, self.height()))

        x = field_bottom.x()
        y = field_bottom.y() + 2

        margin = 8
        min_height = min(
            desired_height,
            row_height * min(3, visible_rows) + 6,
        )

        # Keep the popup on-screen horizontally.
        if x + desired_width > available.right() - margin + 1:
            x = available.right() - desired_width - margin + 1
        x = max(available.left() + margin, x)

        space_below = available.bottom() - y - margin + 1

        # Prefer placement directly below the field. Because the popup is now
        # capped to a small number of rows, this is the normal path.
        if space_below >= min_height:
            desired_height = min(desired_height, space_below)
        else:
            # Only fall back above when there truly is not enough usable space.
            space_above = field_top.y() - available.top() - margin
            if space_above > space_below:
                desired_height = min(desired_height, space_above)
                y = field_top.y() - desired_height - 2
            else:
                desired_height = max(row_height + 6, space_below)

        popup.setGeometry(
            QRect(
                int(x),
                int(y),
                int(desired_width),
                int(max(row_height + 6, desired_height)),
            )
        )

        # The item view itself should use the popup width and rely on the
        # vertical scrollbar for long model lists.
        view.setMinimumWidth(max(0, int(desired_width) - 2))
        view.setMaximumHeight(max(row_height + 4, int(desired_height) - 2))


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isChecked():
            track = QColor("#4F7DF3")
            knob_x = 18
        else:
            track = QColor("#8B93A1")
            knob_x = 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), 11, 11)

        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(knob_x, 3, 16, 16)


class ThemeToggle(QAbstractButton):
    """Animated light / dark theme switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(56, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("切换深色 / 浅色模式")

        # 0.0 = light/left, 1.0 = dark/right.
        self._position = 0.0
        self._position_animation = QPropertyAnimation(self, b"position", self)
        self._position_animation.setDuration(180)
        self._position_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_position)

    def _get_position(self) -> float:
        return self._position

    def _set_position(self, value: float) -> None:
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    position = Property(float, _get_position, _set_position)

    def _animate_position(self, checked: bool) -> None:
        self._position_animation.stop()
        self._position_animation.setStartValue(self._position)
        self._position_animation.setEndValue(1.0 if checked else 0.0)
        self._position_animation.start()

    def set_position_immediate(self, value: float) -> None:
        """Synchronize the knob without animation, useful during startup."""
        self._position_animation.stop()
        self._set_position(value)

    @staticmethod
    def _mix_color(a: str, b: str, t: float) -> QColor:
        ca = QColor(a)
        cb = QColor(b)
        t = max(0.0, min(1.0, t))
        return QColor(
            round(ca.red() + (cb.red() - ca.red()) * t),
            round(ca.green() + (cb.green() - ca.green()) * t),
            round(ca.blue() + (cb.blue() - ca.blue()) * t),
            round(ca.alpha() + (cb.alpha() - ca.alpha()) * t),
        )

    def _draw_sun(self, painter: QPainter, cx: float, cy: float, opacity: float) -> None:
        if opacity <= 0.001:
            return
        painter.save()
        painter.setOpacity(opacity)
        painter.setPen(
            QPen(
                QColor("#F4A62A"),
                1.7,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))
        rays = [
            ((0, -8), (0, -6)), ((0, 8), (0, 6)),
            ((-8, 0), (-6, 0)), ((8, 0), (6, 0)),
            ((-5.7, -5.7), (-4.3, -4.3)), ((5.7, 5.7), (4.3, 4.3)),
            ((5.7, -5.7), (4.3, -4.3)), ((-5.7, 5.7), (-4.3, 4.3)),
        ]
        for start, end in rays:
            painter.drawLine(
                QPointF(cx + start[0], cy + start[1]),
                QPointF(cx + end[0], cy + end[1]),
            )
        painter.restore()

    def _draw_moon(self, painter: QPainter, cx: float, cy: float, opacity: float) -> None:
        if opacity <= 0.001:
            return
        painter.save()
        painter.setOpacity(opacity)
        moon = QPainterPath()
        moon.addEllipse(QRectF(cx - 6, cy - 6, 12, 12))
        cut = QPainterPath()
        cut.addEllipse(QRectF(cx - 2, cy - 7, 11, 11))
        painter.fillPath(moon.subtracted(cut), QColor("#FFD166"))
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        t = self._position

        # The switch itself also blends its colors while the knob is moving.
        track_color = self._mix_color("#EEF2FA", "#252A35", t)
        border_color = self._mix_color("#DDE3EE", "#353C49", t)
        knob_color = self._mix_color("#FFFFFF", "#343B49", t)

        track_rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, 16, 16)

        knob_size = 26
        knob_x = 3 + (self.width() - knob_size - 6) * t
        knob_rect = QRectF(knob_x, 3, knob_size, knob_size)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)

        cx = knob_rect.center().x()
        cy = knob_rect.center().y()

        # Cross-fade sun/moon while the knob glides across the track.
        self._draw_sun(painter, cx, cy, 1.0 - t)
        self._draw_moon(painter, cx, cy, t)
        painter.end()


class ThemeFadeOverlay(QWidget):
    """Paint-only snapshot overlay used for a stable theme cross-fade.

    Using a QWidget that paints the cached pixmap itself avoids the extra
    QGraphicsOpacityEffect composition pass.  That combination can visibly
    "jump" for frameless translucent windows with drop shadows on Windows.
    The overlay is never inserted into a layout, so it cannot influence any
    widget geometry while the theme stylesheet is being replaced.
    """

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._fade_opacity = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _get_fade_opacity(self) -> float:
        return self._fade_opacity

    def _set_fade_opacity(self, value: float) -> None:
        self._fade_opacity = max(0.0, min(1.0, float(value)))
        self.update()

    fadeOpacity = Property(float, _get_fade_opacity, _set_fade_opacity)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setOpacity(self._fade_opacity)
        # QWidget.grab() returns a DPR-aware pixmap. Drawing it into the exact
        # logical widget rect keeps the snapshot aligned on HiDPI displays.
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.end()


class SmoothProgressBar(QWidget):
    """Self-painted determinate / indeterminate progress bar.

    The whole track is repainted on every frame instead of moving a child
    widget with setGeometry(). This avoids stale-pixel trails on frameless,
    translucent Windows windows.
    """

    def __init__(
        self,
        parent=None,
        *,
        bar_height: int = 7,
        segment_ratio: float = 0.22,
        min_segment: float = 48.0,
        track_kind: str = "soft",
    ):
        super().__init__(parent)
        self._display_progress = 0.0
        self._phase = 0.0
        self._indeterminate = False
        self._segment_ratio = float(segment_ratio)
        self._min_segment = float(min_segment)
        self._track_kind = str(track_kind)

        self.setFixedHeight(int(bar_height))
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self._progress_animation = QPropertyAnimation(
            self,
            b"displayProgress",
            self,
        )
        self._progress_animation.setDuration(300)
        self._progress_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

    def _get_display_progress(self) -> float:
        return self._display_progress

    def _set_display_progress(self, value: float) -> None:
        self._display_progress = max(0.0, min(100.0, float(value)))
        self.update()

    displayProgress = Property(
        float,
        _get_display_progress,
        _set_display_progress,
    )

    def set_progress(self, value: float, *, animate: bool = True) -> None:
        value = max(0.0, min(100.0, float(value)))
        self._indeterminate = False
        self._progress_animation.stop()

        if not animate:
            self._set_display_progress(value)
            return

        if abs(self._display_progress - value) < 0.01:
            self.update()
            return

        self._progress_animation.setStartValue(self._display_progress)
        self._progress_animation.setEndValue(value)
        self._progress_animation.start()

    def set_indeterminate(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._indeterminate == enabled:
            return
        self._indeterminate = enabled
        if enabled:
            self._progress_animation.stop()
        self.update()

    def set_phase(self, value: float) -> None:
        self._phase = max(0.0, min(1.0, float(value)))
        self.update()

    def _track_color(self) -> QColor:
        dark = getattr(self.window(), "theme", "light") == "dark"
        if self._track_kind == "border":
            return QColor("#2A303A" if dark else "#E1E5EC")
        return QColor("#202631" if dark else "#F1F4FA")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = float(self.width())
        height = float(self.height())
        if width <= 0.0 or height <= 0.0:
            painter.end()
            return

        track_rect = QRectF(0.0, 0.0, width, height)
        radius = height / 2.0

        # Paint the entire track first. Any pixels from the previous moving
        # segment are overwritten before the new segment is drawn.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._track_color())
        painter.drawRoundedRect(track_rect, radius, radius)

        painter.setBrush(QColor("#4F7DF3"))

        if self._indeterminate:
            import math
            ratio = 0.5 - 0.5 * math.cos(2.0 * math.pi * self._phase)
            segment = min(
                width,
                max(self._min_segment, width * self._segment_ratio),
            )
            travel = max(0.0, width - segment)
            x = travel * ratio
            fill_rect = QRectF(x, 0.0, segment, height)
        else:
            fill_width = width * self._display_progress / 100.0
            if fill_width <= 0.01:
                painter.end()
                return
            fill_rect = QRectF(0.0, 0.0, fill_width, height)

        fill_radius = min(radius, fill_rect.width() / 2.0)
        painter.drawRoundedRect(fill_rect, fill_radius, fill_radius)
        painter.end()


class StatusPill(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("statusPill")
        self.setFixedHeight(36)

        # 胶囊只占自身内容需要的空间，不参与横向拉伸
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        self.dot = QLabel(self)
        self.dot.setObjectName("statusDot")
        self.dot.setFixedSize(7, 7)
        layout.addWidget(self.dot)

        self.label = QLabel("就绪", self)
        self.label.setObjectName("statusText")
        self.label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.label)

        self._update_width()

    def _update_width(self):
        text_width = self.label.fontMetrics().horizontalAdvance(
            self.label.text()
        )

        # 左右边距 28
        # 圆点 7
        # spacing 8
        # 再留一点余量
        width = 28 + 7 + 8 + text_width + 4

        # 最小保持比较协调
        width = max(88, width)

        self.setFixedWidth(width)

    def set_status(self, text: str, error: bool = False) -> None:
        # 不再强制截断文字
        self.label.setText(text)

        self.setToolTip(text)

        self.dot.setProperty("error", error)
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)

        # 状态文字改变后重新计算胶囊宽度
        self._update_width()


class DragArea(QWidget):
    """Area that delegates moving/maximizing to Qt's native window APIs."""

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            handle = window.windowHandle()
            if handle and not window.isMaximized():
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ResizeHandle(QWidget):
    def __init__(self, edges: Qt.Edge, cursor: Qt.CursorShape, parent=None):
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if not window.isMaximized() and window.windowHandle():
                window.windowHandle().startSystemResize(self.edges)
                event.accept()
                return
        super().mousePressEvent(event)


class DropCard(QFrame):
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropCard")

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                suffix = Path(urls[0].toLocalFile()).suffix.lower()
                if suffix in SUPPORTED_MEDIA:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.file_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()
        else:
            event.ignore()


class LogWindow(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("yt-dlp 下载日志")
        self.resize(920, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        box = QTextEdit(self)
        box.setReadOnly(True)
        box.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        box.setFont(QFont(APP_FONT_FAMILY, 10))
        box.setPlainText(text)
        layout.addWidget(box)
