'''The hooks the pets model names: a menu item, and part of a tooltip.'''
from sn.hooks import hook, HookContext

@hook(appliesTo=lambda obj, context: obj.isIndividual())
def sayHello(obj, context:HookContext) -> None:
  '''A menu item: say hello to each animal it acts on.'''
  for vo in context.selection:
    print(f"Hello, {vo.modelObject.name}!")

@hook
def ageTip(obj, context:HookContext) -> str:
  '''For a tooltip: how old it is, if it's known.'''
  age = obj.get("age")
  return f"{age} years old" if age is not None else "age unknown"
