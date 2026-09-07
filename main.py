"""Desktop entry point: python main.py."""

import os

# A terminal previously used by PyQt/Conda may retain plugin paths belonging to
# another Qt build. Let PySide6 select the plugins bundled with its own wheel.
if os.name == "nt":
    os.environ.pop("QT_PLUGIN_PATH", None)
    os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)

from bili_notes.ui import main

if __name__ == "__main__":
    main()
