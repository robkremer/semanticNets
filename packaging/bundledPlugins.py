'''
The bundled plugins' files, for the app (semanticNets.spec) and the .pyz
(makePyz.py): what's in the project's plugins/ folder that's installed (see
sn.plugins.installed(): repeated here, as importing sn would set up its log
file and prefs), and the standard library modules they import -- which
PyInstaller doesn't see, as the plugins are bundled as data (they're imported
from their installed copies, in ~/.sn/plugins).

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import ast, fnmatch, os, sys, tomllib

NOT_INSTALLED = ("__pycache__", "*.pyc", "*.log", ".gitignore", ".DS_Store")
"As sn.plugins.NOT_INSTALLED."

def files(plugins:str) -> list[tuple[str, str]]:
  '''
  :param plugins: The project's plugins folder.
  :returns: The files in it to bundle: (the file, its path in plugins/, with "/").
  '''
  ret = []
  for plugin in sorted(os.listdir(plugins)):
    top = os.path.join(plugins, plugin)
    if not os.path.isfile(os.path.join(top, "plugin.toml")):
      continue
    with open(os.path.join(top, "plugin.toml"), "rb") as f:
      exclude = tomllib.load(f).get("exclude", [])
    for folder, dirs, names in os.walk(top):
      rel = os.path.relpath(folder, top)
      def path(name:str) -> str:
        return (name if rel == "." else os.path.join(rel, name)).replace(os.sep, "/")
      def wanted(name:str) -> bool:
        return not any(fnmatch.fnmatch(name, p) for p in NOT_INSTALLED) and not any(fnmatch.fnmatch(path(name), p) for p in exclude)
      dirs[:] = sorted(d for d in dirs if wanted(d))
      ret += [(os.path.join(folder, n), f"{plugin}/{path(n)}") for n in sorted(names) if wanted(n)]
  return ret

def stdlibImports(pythonFiles:list[str]) -> list[str]:
  '''
  :param pythonFiles: Python files.
  :returns: The standard library modules they import (by absolute imports).
  '''
  ret = set()
  for file in pythonFiles:
    with open(file, encoding="utf-8") as f:
      tree = ast.parse(f.read(), file)
    for node in ast.walk(tree):
      names = [a.name for a in node.names] if isinstance(node, ast.Import) \
        else [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
      ret.update(n for n in names if n.split(".")[0] in sys.stdlib_module_names)
  return sorted(ret)

if __name__ == "__main__": # (to see what they are)
  root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugins")
  found = files(root)
  print("\n".join(p for _, p in found))
  print("imports:", ", ".join(stdlibImports([f for f, _ in found if f.endswith(".py")])))
