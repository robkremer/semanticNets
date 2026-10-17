# -*- mode: python ; coding: utf-8 -*-
'''
PyInstaller spec for the stand-alone "Semantic Nets.app" (see build.xml's "app"
target). Run from the project's top folder:

  .venv-build/bin/pyinstaller --noconfirm --distpath dist --workpath build/pyinstaller packaging/semanticNets.spec

The app is the graphical editor (sn/__main__.py) with its own Python, Tk and
clingo inside. It bundles, at the same relative places sn.resourcePath() looks:

  - sn/examples/  the example models (package data), installed on the first launch;
  - plugins/    the plugins that come with it (pythonParser, XMLreader: see
                sn.plugins), copied to ~/.sn/plugins when the app starts;
  - help/       the HTML documentation (built by the "doc" target), for the Help menu.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")
UTILS = os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))

import platform, re, sys
sys.path[:0] = [SRC, UTILS]

def _snConstant(name:str) -> str:
  # (read from sn/__init__.py's text: importing sn would set up its log file and prefs)
  with open(os.path.join(SRC, "sn", "__init__.py"), encoding="utf-8") as f:
    return re.search(rf'^{name}\s*=\s*"([^"]*)"', f.read(), re.M).group(1)
NAME, VERSION = _snConstant("NAME"), _snConstant("VERSION")

TARGET_ARCH = os.environ.get("SN_TARGET_ARCH") or None
"""The app's architecture: unset for the building Mac's (eg: arm64), or "universal2"
for Intel and Apple silicon both (see build.xml's "appUniversal" target: its
compiled packages must be universal too -- packaging/makeUniversalWheels.py)."""

MIN_MACOS = {"x86_64": "10.15", "arm64": "11.0"}
"The macOS each architecture's bundled binaries (Python, Tk, clingo, ...) need."

datas = [
  (os.path.join(SRC, "sn", "model", "clingoReasoner.lp"), os.path.join("sn", "model")),
  (os.path.join(SRC, "sn", "model", "baseRules.snm"), os.path.join("sn", "model")),
  (os.path.join(SRC, "sn", "examples"), os.path.join("sn", "examples")),
]
# The bundled plugins: as files (they're imported from their installed copies,
# in ~/.sn/plugins, not from the app): see bundledPlugins.py.
sys.path.insert(0, SPECPATH)
import bundledPlugins
pluginFiles = bundledPlugins.files(os.path.join(ROOT, "plugins"))
datas += [(f, os.path.dirname(os.path.join("plugins", p))) for f, p in pluginFiles]

html = os.path.join(ROOT, "sphinx", "build", "html")
if os.path.isdir(html):
  datas.append((html, "help"))
else:
  print(f"WARNING: no documentation in {html}: the app's Help menu won't have it (run the \"doc\" target first).")

# Saved files name their classes by module (eg: "sn.view.graphics.sngView.SNGView"),
# and serialization strategies are found by name: include every module, not just
# the ones imported statically.
UNUSED = {"rtValuesDialog.py"} # (pythonUtils modules the app doesn't use, and that need matplotlib)

def _modules(top:str, package:str) -> list[str]:
  # (found from the files, not by importing them as collect_submodules() would:
  # importing sn sets up its log file and saves its prefs at exit)
  ret = []
  for folder, dirs, files in os.walk(os.path.join(top, package)):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    rel = os.path.relpath(folder, top).replace(os.sep, ".")
    ret += [rel if f == "__init__.py" else f"{rel}.{f[:-3]}" for f in files
            if f.endswith(".py") and not f.startswith("x_") and f not in UNUSED]
  return ret
hiddenimports = _modules(SRC, "sn") + _modules(UTILS, "util") + bundledPlugins.stdlibImports([f for f, _ in pluginFiles if f.endswith(".py")]) \
  + ["_cffi_backend", "clingo._clingo"] # (clingo's compiled core is a cffi extension: PyInstaller doesn't see that it needs cffi)

a = Analysis(
  [os.path.join(SRC, "sn", "__main__.py")],
  pathex=[SRC, UTILS],
  datas=datas,
  hiddenimports=hiddenimports,
  excludes=["matplotlib", "numpy", "mypyc", "util.rtValuesDialog"], # (not used: keep the app small)
  noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
  pyz, a.scripts, [],
  exclude_binaries=True,
  name="Semantic Nets",
  console=False,          # a windowed (GUI) app
  argv_emulation=False,   # (Tk itself receives the Finder's "open document" events: see guiApp.onOpenDocument())
  codesign_identity=None, # ad hoc signing
  target_arch=TARGET_ARCH,
  icon=os.path.join(SPECPATH, "sn.icns"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Semantic Nets")

DOCUMENT_TYPES = [
  {"CFBundleTypeName": "Semantic Nets View", "CFBundleTypeRole": "Editor",
   "CFBundleTypeExtensions": ["snv"], "LSHandlerRank": "Owner",
   "CFBundleTypeIconFile": "sn.icns"},
  {"CFBundleTypeName": "Semantic Nets Model", "CFBundleTypeRole": "Editor",
   "CFBundleTypeExtensions": ["snm"], "LSHandlerRank": "Owner",
   "CFBundleTypeIconFile": "sn.icns"},
]

app = BUNDLE(
  coll,
  name="Semantic Nets.app",
  icon=os.path.join(SPECPATH, "sn.icns"),
  bundle_identifier="com.robkremer.semanticnets",
  version=VERSION,
  info_plist={
    "CFBundleName": NAME,
    "CFBundleDisplayName": NAME,
    "CFBundleShortVersionString": VERSION,
    "CFBundleVersion": VERSION,
    "CFBundleDocumentTypes": DOCUMENT_TYPES,
    "NSHighResolutionCapable": True,
    # (what the bundled binaries need -- see MIN_MACOS -- for each architecture the app has)
    "LSMinimumSystemVersion": MIN_MACOS["x86_64"] if TARGET_ARCH == "universal2" else MIN_MACOS[TARGET_ARCH or platform.machine()],
    **({"LSMinimumSystemVersionByArchitecture": MIN_MACOS} if TARGET_ARCH == "universal2" else {}),
    "NSHumanReadableCopyright": "(c) 2023-2026 Rob Kremer. MIT licence.",
  },
)
