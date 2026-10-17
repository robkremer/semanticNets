'''
Build dist/SemanticNets-<version>.pyz: the editor as a single zip-file
application (see https://docs.python.org/3/library/zipapp.html), for people who
already have Python. Run it with::

  python3.14 SemanticNets-1.0.pyz [file ...]       (or: ... --selftest)

It holds the sn and util packages (pure Python) and their data, and the
bundled plugins (plugins/: see bundledPlugins.py), but not their
compiled dependencies: the person running it needs Python 3.14, with Tk, and
``pip install -r packaging/requirements.txt`` (clingo, ...). Its launcher says so
if they're missing.

Used by build.xml's "pyz" target; run from the project's top folder::

  python3.14 packaging/makePyz.py

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, re, shutil, sys, zipapp

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
UTILS = os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))
STAGE = os.path.join(ROOT, "build", "pyz")
DIST = os.path.join(ROOT, "dist")

UNUSED = {"rtValuesDialog.py"} # (pythonUtils modules the app doesn't use, and that need matplotlib)

LAUNCHER = '''\
# The .pyz's entry point: check the things it can't carry are there, then run
# the editor (sn/__main__.py).
import sys
if sys.version_info < (3, 14):
  sys.exit(f"Semantic Nets needs Python 3.14 or later (this is {sys.version.split()[0]}).")
missing = []
for module, package in (("tkinter", "Python's Tk support"), ("clingo", "clingo"), ("requests", "requests"),
                        ("urllib3", "urllib3"), ("docstring_parser", "docstring_parser")):
  try:
    __import__(module)
  except ImportError:
    missing.append(package)
if missing:
  sys.exit("Semantic Nets needs: " + ", ".join(missing) +
           ". Install them with: python3 -m pip install clingo requests urllib3 docstring_parser")
import runpy
runpy.run_module("sn", run_name="__main__", alter_sys=True)
'''

def ignore(folder:str, names:list[str]) -> list[str]:
  return [n for n in names if n == "__pycache__" or n == "help" or n.endswith((".log", ".pyc"))
          or n.startswith("x_") or n in UNUSED]

def version() -> str:
  with open(os.path.join(SRC, "sn", "__init__.py"), encoding="utf-8") as f:
    return re.search(r'^VERSION\s*=\s*"([^"]*)"', f.read(), re.M).group(1)

def main() -> None:
  shutil.rmtree(STAGE, ignore_errors=True)
  shutil.copytree(os.path.join(SRC, "sn"), os.path.join(STAGE, "sn"), ignore=ignore)
  shutil.copytree(os.path.join(UTILS, "util"), os.path.join(STAGE, "util"), ignore=ignore)
  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
  import bundledPlugins
  for file, path in bundledPlugins.files(os.path.join(ROOT, "plugins")):
    os.makedirs(os.path.dirname(os.path.join(STAGE, "plugins", path)), exist_ok=True)
    shutil.copy(file, os.path.join(STAGE, "plugins", path))
  with open(os.path.join(STAGE, "__main__.py"), "w", encoding="utf-8") as f:
    f.write(LAUNCHER)
  os.makedirs(DIST, exist_ok=True)
  target = os.path.join(DIST, f"SemanticNets-{version()}.pyz")
  zipapp.create_archive(STAGE, target, interpreter="/usr/bin/env python3.14", compressed=True)
  print("wrote", target)

if __name__ == "__main__":
  main()
