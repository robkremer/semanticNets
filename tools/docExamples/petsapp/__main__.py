'''
Make the pets model (see *build*), and open a view of it in the editor,
arranged as a tree by isa:

  python3.14 -m petsapp [pets.snm]
'''
import sn # (first: it sets up logging)
import os, sys
from sn.view.graphics.guiApp import Application
from sn.view.graphics.treeLayout import TreeLayout
import petsapp.hooks       # (its hooks: the model's menu item and tooltip name them)
import petsapp.gridLayout  # (adds "grid" to the view's layout menu)
from petsapp.build import buildPets

def main() -> None:
  path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "pets.snm")
  if os.path.exists(path):
    sys.exit(f"{path} is there already")
  buildPets(path)
  app = Application()
  def start() -> None:
    window = app.openWindow(path)    # (a new view of it: pets.snv)
    view = window.view
    view.context.visibility("system objects", "hide")
    view.showAllModel()
    TreeLayout(view, relation="isa", direction="down").arrange(animate=False)
    view.save()
  app.after(300, start)
  app.run()

if __name__ == "__main__":
  main()
