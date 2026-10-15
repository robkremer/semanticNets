'''A layout of its own: "grid", on the view's layout menu.'''
from sn.view.graphics.layout import LayoutHeuristic, LayoutParameter, registerLayout, layoutSize, STATIC
from sn.view.graphics.vnodes import VNode

@registerLayout
class GridLayout(LayoutHeuristic):
  '''Arrange the nodes shown in a grid, in order of name.'''
  NAME = "grid"
  CATEGORIES = (STATIC,)
  PARAMETERS = (
    LayoutParameter("columns", "Columns", "int", 4),
    LayoutParameter("spacing", "Space between neighbours", "int", 40),
  )

  def targets(self):
    nodes = [vo for vo in self.view.values()
             if isinstance(vo, VNode) and vo.modelObject is not None and not vo.isHidden()
             and not vo.isContextWindow()]
    nodes.sort(key=lambda vo: str(vo.modelObject.name).lower())
    cols, gap = self.params["columns"], self.params["spacing"]
    width = max((layoutSize(vo)[0] for vo in nodes), default=0) + gap
    height = max((layoutSize(vo)[1] for vo in nodes), default=0) + gap
    return {vo: (gap + (i % cols) * width, gap + (i // cols) * height) for i, vo in enumerate(nodes)}
