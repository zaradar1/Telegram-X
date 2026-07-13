import os

try:
    from com.chaquo.python import Python
    _context = Python.getPlatform().getApplication()
    APP_DIR = str(_context.getFilesDir())
    _external = _context.getExternalFilesDir(None)
    DOWNLOAD_DIR = str(_external) if _external else os.path.join(APP_DIR, "downloads")
    ON_ANDROID = True
except ImportError:
    APP_DIR = os.path.join(os.path.expanduser("~"), ".telegram_manager")
    DOWNLOAD_DIR = os.path.join(APP_DIR, "downloads")
    ON_ANDROID = False

os.makedirs(APP_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DB_PATH = os.path.join(APP_DIR, "manager.db")
