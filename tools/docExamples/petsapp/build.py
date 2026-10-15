'''The pets model, made in code: types, individuals, relations, an attribute, a
transitive relation type -- and a menu item and tooltip, from hooks.'''
from sn.model.model import Model, Node, Relation

def buildPets(path:str) -> Model:
  '''Make a small model of pets, and save it at *path* (a new file).'''
  m = Model(path)
  animal = Node(m, [m.NODE], name="animal")
  animal["vis/shape"] = "RoundedRectangle"
  animal["vis/fillColor"] = "LightGoldenrod1"
  dog = Node(m, [animal], name="dog")
  cat = Node(m, [animal], name="cat")
  chases = Relation(m, [m.RELATION], animal, animal, name="chases")
  hasAncestor = Relation(m, [m.RELATION], dog, dog, name="has-ancestor")
  hasAncestor["transitive"] = True
  rex = Node(m, [dog], individual=True, name="rex")
  fido = Node(m, [dog], individual=True, name="fido")
  rover = Node(m, [dog], individual=True, name="rover")
  tom = Node(m, [cat], individual=True, name="tom")
  rex["age"] = 3
  Relation(m, [chases], rex, tom, individual=True)
  Relation(m, [hasAncestor], fido, rex, individual=True)
  Relation(m, [hasAncestor], rex, rover, individual=True)
  # behaviour that lasts: a menu item and a tooltip, on every animal
  animal[".menu/Say hello"] = "petsapp.hooks:sayHello"
  animal["vis/tooltip"] = "$name\n$(petsapp.hooks:ageTip)"
  m.save()
  return m
