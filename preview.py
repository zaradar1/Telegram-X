"""Media preview widgets for the Files tab (Tkinter)."""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from typing import Optional

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
TEXT_EXTS = {".txt", ".md", ".log", ".json", ".csv"}


def show_image_preview(parent, file_path: str, max_size=(400, 400)) -> Optional[tk.Label]:
    try:
        from PIL import Image, ImageTk
    except ImportError:
        ttk.Label(parent, text="Install Pillow to preview images").pack()
        return None
    img = Image.open(file_path)
    img.thumbnail(max_size)
    photo = ImageTk.PhotoImage(img)
    label = tk.Label(parent, image=photo)
    label.image = photo  # keep a reference so it isn't garbage-collected
    return label


def show_text_preview(parent, file_path: str, max_chars: int = 4000) -> tk.Text:
    txt = tk.Text(parent, wrap="word", height=20, font=("Consolas", 9))
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
    except Exception as e:
        content = f"Could not read file: {e}"
    txt.insert("1.0", content)
    txt.configure(state="disabled")
    return txt


def open_with_system_default(file_path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(file_path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", file_path])
    else:
        subprocess.Popen(["xdg-open", file_path])


def preview_file(parent, file_path: str) -> None:
    """Render the best available preview for file_path inside `parent`,
    falling back to a button that opens it in the OS default app."""
    for child in list(parent.winfo_children()):
        child.destroy()

    ext = os.path.splitext(file_path)[1].lower()
    if not os.path.exists(file_path):
        ttk.Label(parent, text="File not found on disk.").pack(pady=20)
        return

    if ext in IMAGE_EXTS:
        widget = show_image_preview(parent, file_path)
        if widget:
            widget.pack(padx=10, pady=10)
        return

    if ext in TEXT_EXTS:
        show_text_preview(parent, file_path).pack(fill="both", expand=True, padx=10, pady=10)
        return

    ttk.Label(parent, text=f"No inline preview for {ext or 'this file type'}.").pack(pady=10)
    ttk.Button(parent, text="Open in default app",
               command=lambda: open_with_system_default(file_path)).pack()
