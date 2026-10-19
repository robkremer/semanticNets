'''
Run *Semantic Nets*' graphical editor: ``python -m sn [file ...]``. This is
also the entry point of the packaged app, and of the .pyz.

``--selftest`` instead checks that the program's parts are all there and work,
without opening a window: it reasons over a copy of the bundled family example
and checks the conclusions, and installs the bundled plugins (in a scratch
folder), imports all their modules, and makes a model with each (see
*selftestPlugins()*) -- as the "app" and "pyz" ant targets do after a build.
It exits with 0 if all's well, and 1 if not.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import sys

def selftest() -> int:
  '''
  :returns: The exit status: 0 if the reasoner's conclusions about the family
    example are as expected, 1 if not.
  '''
  import atexit, shutil, tempfile
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
    expected = ["-has-brother->", "-has-uncle->", "Violations: 0 error(s)"] # (alice has-brother bob, so carol has-uncle bob)
    missing = [e for e in expected if e not in report] + selftestPlugins(folder)
    import platform
    print("selftest:", ("FAILED: missing " + ", ".join(missing)) if missing else "ok", f"({platform.machine()})")
    return 1 if missing else 0
  finally:
    shutil.rmtree(folder, ignore_errors=True)

def selftestPlugins(folder:str) -> list[str]:
  '''
  Install the bundled plugins in *folder* (see *sn.plugins.installBundled()*),
  import every module in them -- catching any standard library module the
  build left out -- and make a model with each: XMLreader of its books.xml,
  pythonParser of its own parser.py. (Not registered: there's no editor.)

  :param folder: A scratch folder.
  :returns: What's wrong: empty if nothing is.
  '''
  import importlib, os, traceback
  from sn import plugins
  target = os.path.join(folder, "plugins")
  try:
    plugins.installBundled(target=target)
    found = [m.id for m in plugins.manifests(target)]
    problems = [f"the {p} plugin" for p in ("XMLreader", "pythonParser") if p not in found]
    plugins.namespace(target)
    for id in found:
      for dirpath, dirs, files in os.walk(os.path.join(target, id)):
        dirs[:] = [d for d in dirs if os.path.isfile(os.path.join(dirpath, d, "__init__.py"))] # (packages only: not examples/)
        rel = os.path.relpath(dirpath, target).replace(os.sep, ".")
        for f in sorted(files):
          if f.endswith(".py"):
            importlib.import_module(f"{plugins.NAMESPACE}.{rel}" + ("" if f == "__init__.py" else f".{f[:-3]}"))
    if "XMLreader" in found:
      reader = importlib.import_module(f"{plugins.NAMESPACE}.XMLreader.reader")
      xml, ontology = reader.buildModel(os.path.join(target, "XMLreader", "examples", "books.xml"), os.path.join(folder, "books_xml.snm"))
      print(f"XMLreader: {len(list(xml.values()))} objects, {len(list(ontology.values()))} in its ontology")
    if "pythonParser" in found:
      parser = importlib.import_module(f"{plugins.NAMESPACE}.pythonParser.parser")
      code = parser.buildModel(os.path.join(folder, "parser_py.snm"), parser.readModules([parser.__file__]))
      print(f"pythonParser: {len(list(code.values()))} objects")
    return problems
  except Exception:
    traceback.print_exc()
    return ["the plugins (see above)"]

if __name__ == "__main__":
  if "--selftest" in sys.argv[1:]:
    sys.exit(selftest())
  from sn.view.graphics.guiApp import main
  main()
