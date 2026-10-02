'''
dmgbuild settings for the installer disk image (see build.xml's "dmg" target):
the app, an Applications shortcut to drag it to, and a "Read Me First".

  dmgbuild -s packaging/dmgSettings.py -D app="dist/Semantic Nets.app" "Semantic Nets" dist/SemanticNets-1.0.dmg

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os.path

application = defines.get("app", "dist/Semantic Nets.app") # noqa: F821 (dmgbuild supplies "defines")
appName = os.path.basename(application)
readMe = defines.get("readme", "packaging/ReadMeFirst.txt") # noqa: F821

format = "UDZO"           # compressed
filesystem = "HFS+"
files = [application, (readMe, "Read Me First.txt")]
symlinks = {"Applications": "/Applications"}
badge_icon = None
icon = defines.get("icon", "packaging/sn.icns") # noqa: F821 (the volume's icon)

default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
window_rect = ((200, 160), (620, 360))
icon_size = 96
text_size = 13
icon_locations = {
  appName: (150, 140),
  "Applications": (470, 140),
  "Read Me First.txt": (310, 280),
}
