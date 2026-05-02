"""
Runtime hook for OpenCV in bundled macOS app.

OpenCV's loader checks `sys.OpenCV_REPLACE_SYS_PATH_0` and, when set, inserts
its binary extension path at the front of `sys.path`. This avoids recursive
re-import of the `cv2` package from the app bundle parent directory.
"""

import sys


sys.OpenCV_REPLACE_SYS_PATH_0 = True
