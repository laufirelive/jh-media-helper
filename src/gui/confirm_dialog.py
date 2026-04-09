# -*- coding: utf-8 -*-
"""确认对话框：使用标准 Yes/No 按钮，避免 macOS 上 addButton+clickedButton 偶发不弹窗。"""

from PyQt6.QtWidgets import QMessageBox, QWidget


def confirm_action(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    default_confirm: bool = False,
) -> bool:
    """
    显示「确定 / 取消」；点「确定」返回 True。
    default_confirm=False 时默认选中「取消」，减少误触。
    """
    mb = QMessageBox(parent)
    mb.setWindowTitle(title)
    mb.setText(text)
    mb.setIcon(QMessageBox.Icon.Question)
    mb.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    mb.setDefaultButton(
        QMessageBox.StandardButton.Yes
        if default_confirm
        else QMessageBox.StandardButton.No
    )
    yes_btn = mb.button(QMessageBox.StandardButton.Yes)
    no_btn = mb.button(QMessageBox.StandardButton.No)
    if yes_btn is not None:
        yes_btn.setText("确定")
    if no_btn is not None:
        no_btn.setText("取消")
    ret = mb.exec()
    if ret == QMessageBox.StandardButton.Yes:
        return True
    try:
        return QMessageBox.StandardButton(ret) == QMessageBox.StandardButton.Yes
    except (ValueError, TypeError):
        return False
