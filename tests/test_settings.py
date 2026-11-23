import os, sys, time, faulthandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
faulthandler.dump_traceback_later(20, exit=True)
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
t = time.time()
from streamgrab.settings_dialog import SettingsDialog
print("import", time.time() - t, flush=True)
s = QSettings("StreamGrabTest", "StreamGrabTest")
t = time.time()
d = SettingsDialog(s)
print("construct", time.time() - t, flush=True)
QTimer.singleShot(4000, lambda: (print("version label:", d.ver.text(), flush=True), app.quit()))
d.show()
app.exec()
print("ok")
