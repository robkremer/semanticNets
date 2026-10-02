'''
Make the build venv's compiled packages universal (Intel + Apple silicon), so
PyInstaller can build a universal app (see build.xml's "universalWheels" and
"appUniversal" targets).

Python itself (python.org's) and Tk are universal already, as are some packages'
wheels (eg: charset_normalizer). But PyPI has only separate x86_64 and arm64
wheels of clingo and cffi: this downloads both of the installed version of each,
fuses them (delocate-merge) into a universal2 wheel, and installs that in their
place. (The universal2 packages work for an arm64-only build too.)

Run with the build venv's Python, from the project's top folder::

  .venv-build/bin/python packaging/makeUniversalWheels.py

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import glob, importlib.metadata, os, shutil, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WHEELS = os.path.join(ROOT, "build", "wheels")
PACKAGES = ["clingo", "cffi"]
"The packages whose PyPI wheels aren't universal."

PLATFORMS = {"arm64": "macosx_11_0_arm64", "x86_64": "macosx_10_15_x86_64"}
PYTHON = f"{sys.version_info.major}{sys.version_info.minor}" # eg: "314"

def pip(*args:str) -> None:
  subprocess.run([sys.executable, "-m", "pip", *args], check=True)

def main() -> None:
  shutil.rmtree(WHEELS, ignore_errors=True)
  merged = []
  for package in PACKAGES:
    version = importlib.metadata.version(package)
    found = {}
    for arch, platform in PLATFORMS.items():
      folder = os.path.join(WHEELS, arch)
      pip("download", "--quiet", "--no-deps", "--only-binary=:all:", "--implementation", "cp",
          "--python-version", PYTHON, "--abi", f"cp{PYTHON}", "--platform", platform,
          "--dest", folder, f"{package}=={version}")
      [found[arch]] = glob.glob(os.path.join(folder, f"{package}-{version}-*.whl"))
    out = os.path.join(WHEELS, "universal2")
    subprocess.run([os.path.join(os.path.dirname(sys.executable), "delocate-merge"),
                    "-w", out, found["arm64"], found["x86_64"]], check=True)
    [wheel] = glob.glob(os.path.join(out, f"{package}-{version}-*.whl"))
    merged.append(wheel)
  pip("install", "--quiet", "--force-reinstall", "--no-deps", *merged)
  for wheel in merged:
    print("installed", os.path.basename(wheel))

if __name__ == "__main__":
  main()
