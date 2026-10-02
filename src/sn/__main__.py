'''
Run *Semantic Nets*' graphical editor: ``python -m sn [file ...]``. This is
also the entry point of the packaged app, and of the .pyz.

``--selftest`` instead checks that the program's parts are all there and work,
without opening a window: it reasons over a copy of the bundled family example
and checks the conclusions (as the "app" and "pyz" ant targets do after a
build). It exits with 0 if all's well, and 1 if not.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import sys

def selftest() -> int:
  '''
  :returns: The exit status: 0 if the reasoner's conclusions about the family
    example are as expected, 1 if not.
  :rtype: int
  '''
  import atexit, os, shutil, tempfile
  from pathlib import Path
  import sn
  from sn.model.model import Model
  from sn.model.reasoner import reason
  atexit.unregister(sn.savePrefsIfChanged) # (a test mustn't touch the user's preferences or models)
  atexit.unregister(sn.saveAtExit)
  folder = tempfile.mkdtemp()
  try:
    sn.copyExamples(folder, ["family.snm", "family.snv"])
    model = Model.getDB(Path(folder, "family.snm").as_uri())
    report = reason(model).report(model)
    print(report)
    expected = ["-brother->", "-uncle->", "Violations: 0 error(s)"]
    missing = [e for e in expected if e not in report]
    import platform
    print("selftest:", ("FAILED: missing " + ", ".join(missing)) if missing else "ok", f"({platform.machine()})")
    return 1 if missing else 0
  finally:
    shutil.rmtree(folder, ignore_errors=True)

if __name__ == "__main__":
  if "--selftest" in sys.argv[1:]:
    sys.exit(selftest())
  from sn.view.graphics.guiApp import main
  main()
