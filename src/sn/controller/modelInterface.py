#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
#                                                                               #
# Permission is hereby granted, free of charge, to any person obtaining a copy  #
# of this software and associated documentation files (the "Software"), to deal #
# in the Software without restriction, including without limitation the rights  #
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     #
# copies of the Software, and to permit persons to whom the Software is         #
# furnished to do so, subject to the following conditions:                      #
#                                                                               #
# The above copyright notice and this permission notice shall be included in all#
# copies or substantial portions of the Software.                               #
#                                                                               #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    #
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      #
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   #
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER        #
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, #
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE #
# SOFTWARE.                                                                     #
#################################################################################
from __future__ import annotations
import sn
from sn.model.model import GraphObject, Model, Node, Relation, GORef,\
  Collection, IsaIndividual
#import util.persistence.pRef as pRef
#from util.persistence.pRef import PReference
import logging
from types import NoneType
from typing import override, Any, Optional, Iterable, Callable, cast
from util.commandParser import TopCommandParser, CommandContext, Command
from util.persistence.serialize import SerializationStrategy
from util.utils import getClass, fixURL, isValidURL, urlExists
from util.attribute import Attribute, Restriction
from util.persistence.pRef import PRDb, DuplicateNameError
from sn import snPrefs
from util.observer import Subject


logger:sn.SNLogger = sn.getLogger(__name__)

'''
Created on May 14, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>

'''
class ConvertingDict(dict[str, Any]):
  def __init__(self, context:ModelContext, iterable:Iterable=[]):
    super().__init__(iterable)
    self.context = context
    
  def typeCheck(self, obj:Any, typ:type) -> Any:
    if not isinstance(obj, typ):
      raise TypeError(f'Expected object of type {type.__name__}, but got type {obj.__class__.__name__}.')
    return obj
    
  @override
  def __setitem__(self, key:str, value:Any):
    if key == "model" and not isinstance(value, Model):
      return super().__setitem__(key, Model.getDB(value))
    if (key == "node" or key.endswith("_node")) and isinstance(value, str):
      return super().__setitem__(key, self.typeCheck(self.context.decoders["GraphObject"](value), Node))
    if (key == "relation" or key.endswith("_relation")) and isinstance(value, str):
      return super().__setitem__(key, self.typeCheck(self.context.decoders["GraphObject"](value), Relation))
    if (key == "object" or key.endswith("_object")) and isinstance(value, str):
      return super().__setitem__(key, self.typeCheck(self.context.decoders["GraphObject"](value), GraphObject))
    else:
      return super().__setitem__(key, value)

class ModelContext(CommandContext):
  commandSynonyms:dict[str, Iterable[str]] = {
    "query"          :["?"],
    "assert"         :["!", "declare"],
    "save"           :["write"]}
  
  optionSynonyms:dict[str, dict[str, list[str]]] = {
    "show"           :{"detail"    : ["-d"],
                       "model"     : ["-m"],
                       "format"    : ["-f"]},
    "save"           :{"model"     : ["-m"],
                       "url"       : ["-u", "--file"],
                       "overwrite" : ["-o"],
                       "format"    : ["-f"]},
    "_New_node"      :{"name"      : ["-n"],
                       "individual": ["-i", "--object", "-o"],
                       "type"      : ["-t", "--class", "-c"],
                       "model"     : ["-m"]},
    "_New_relation"  :{"name"      : ["-n"],
                       "individual": ["-i", "--object", "-o"],
                       "type"      : ["-t", "--class", "-c"],
                       "model"     : ["-m"]},
    "query"          :{"model"     : ["-m"],
                       "astree"    : ["-t"],
                       "keepdups"  : ["-k"]},
    "validate"       :{"model"     : ["-m"]},
    }
  
  commandHelp:dict[str,str] = CommandContext.commandHelp | {
    "new": "Create a new graphic object in the default model or another model",
    "set": "Sets the values of or creates various entities like object attributes.",
    "get": "Returns the values of various entities like object attributes.",
    }
  
  def __init__(self, model:Model):
    super().__init__(TopCommandParser("sn", defaults=ConvertingDict(self)))
    assert isinstance(self.parser, TopCommandParser)
    self.defaults["model"] = model
    
  @override
  def _defineDecoders(self):
    def getModel(s:str) -> Model:
      ret:Model = cast(Model, GORef.eval(s))
      assert isinstance(ret, Model)
      return ret
    def getGO(s:str, d:dict, **kwargs) -> GraphObject:
      try:
        # otherParams = kwargs.get("params")
        # model = otherParams["model"] if otherParams is not None else None
        ret = GORef.eval(s, d["model"] if kwargs.get("model") is None else kwargs["model"])
        # ret = GORef.eval(s, d["model"] if model is None else model)
        assert isinstance(ret, GraphObject)
        return ret
      except Exception as ex:
        #print(ex)
        raise ex
    super()._defineDecoders()
    #self.decoders["GraphObject"] = lambda s, d=self.defaults, **kwargs: GORef.eval(s, d["model"] if kwargs.get("model") is None else kwargs["model"]) #type: ignore[misc]
    self.decoders["GraphObject"] = lambda s, d=self.defaults, **kwargs: getGO(s,d,**kwargs)
    self.decoders["Model"] = getModel #lambda s: GORef.eval(s)
    
  def cache(self):
    '''
    Show models in memory.
    '''
    return Model.AllDBs
    
  def validate(self, object:GraphObject|Model|None=None, /, model:Model|None=None) -> list[str]|list[tuple[GraphObject,list[str]]]:
    '''
    Checks the consistency of a Model or a GraphObject.

    :param object: The object to check. By default, checks the default model.
    :type object: GraphObject|Model|None
    :param model: The model context in which to interpret *object* if necessary.
    :type model: Model
    '''
    if object is not None and type(object) is str: # the environment failed to interpret the object
      raise KeyError(f'Object "{object}" not found in model "{model}".')
    ret:list[str]|list[tuple[GraphObject,list[str]]]
    if object is None:
      assert model is not None
      ret = model.validate()
    else:
      ret = object.validate()
    # if not ret:
    #   print("OK")
    return ret


  def show(self, object:GraphObject|Model|None=None, /, model:Model|None=None, detail:bool=False, format:str|None=None) -> str:
    '''
    Prints the string representation of the object to the logger.

    :param object: The object to show.
    :type object: GraphObject|Model|None
    :param model: The model context in which to interpret *object* if necessary.
    :type model: Model
    :param detail: If given, show more detail.
    :type detail: bool
    :param format: Attempts to return the result in the specified format. Currently,
      it accepts "str", "repr", "xml", and "json".
    :returns: The string representation of the object
    :rtype: str
    :raises MalformedIDError: if the form of the ID is not valid.
    :raises ValueError: If it isn't a valid URL.
    :raises FileNotFoundError: If the file or URL does not exist.
    :raises TypeError: If they type of the interpreted object is not a *GraphObject*.
    :raises urllib.error.URLError: If a remote URL cannot be reached.
    
    '''
    if object is not None and type(object) is str: # the environment failed to interpret the object
      raise KeyError(f'Object "{object}" not found in model "{model}".')
    assert isinstance(object, (GraphObject, Model, NoneType)), f'Expected type GraphObject, Model or None, but got type {object.__class__.__name__}.'
    if not isinstance(model, Model): # declared as "|None", but we expect __getattribute__() to fill in the default.
      raise TypeError(f'show(): expected model of type Model, but got type "{model.__class__.__name__}"')

    if object is None:
      object = model
      
    if format is not None:
      format = format.upper()
      if format == "REPR":
        return object.torepr(relativeTo=model)
      if format == "STR":
        return object.tostring(relativeTo=model)
      elif format in ("XML", "JSON"):
        if model is object:
          return SerializationStrategy.tostringx(format, object, assume=[])
        else:
          assert isinstance(object, GraphObject)
          return SerializationStrategy.tostringx(format, object, assume=[object.db])+\
            '\n\n*** Note: The referent of the containing model has been omitted for brevity.'
      else:
        raise ValueError(f'show(): unexpected format "{format}". Choose between "repr", "str", "XML" or "JSON".', )
        
    if detail:
      return object.torepr(relativeTo=model)
    else:
      return object.tostring(relativeTo=model)
    
  def save(self, /, model:Optional[Model]=None, url:Optional[str]=None, overwrite:bool=False, format:str="XML"):
    '''
    Save a model to a file or url.
    
    :param model: The model to save. Defaults to the default model.
    :type model: Model
    :param url: The url or file name to save the model to.
    :type url: str
    :param format: The format to save the file or url in. (Currently "XML" or "JSON".)
    :type format: str
    '''
    assert model is not None
    model.save(url, overwrite=overwrite, format=format)
    
  def get_attribute(self, object:GraphObject, key:list[str]=[], /, model:Optional[Model]=None) -> Any|None:
    '''
    Fetch attributes from a GraphObject.
    
    :param object: The GraphObject to get attributes from.
    :type object: GraphObject
    :param key: Zero or more keys to look up.
    :type key: list[str]
    :param model: The model to look in. Defaults to the default model.
    :type model: Model
    :returns: if exactly *key* is given, it's value is returned. If more than
      one key is given, a *dict* of all those keys-to-values is returned. If 
      no keys are given, *dict* of all keys-to-values is returned.
    :rtype: Any
    '''
    n = len(key)
    if n == 1:
      return object.get(key[0], None)
    return {k:v for k,v in object.items() if ((k in key) if n>0 else True)}
  
  def get_pref(self, key:list[str]=[], /) -> Any|None:
    '''
    Fetch attributes from the Prefs object.
    
    :param key: Zero or more keys to look up.
    :type key: list[str]
    :returns: if exactly *key* is given, it's value is returned. If more than
      one key is given, a *dict* of all those keys-to-values is returned. If 
      no keys are given, a *dict* of all keys-to-values is returned.
    :rtype: Any
    '''
    n = len(key)
    if n == 1:
      return snPrefs.get(key[0], None)
    return {k:v for k,v in snPrefs.items() if ((k in key) if n>0 else True)}
  
  def set_attribute(self, object:GraphObject|None, key:str, value:Any, /, \
                    model:Optional[Model]=None, type:str|None=None, restriction:str|None=None) -> Any|None:
    '''
    Set the attribute of a *GraphObject*.
    
    :param object: The object who's attribute is to be set.
    :type object: GraphObject
    :param key: The key in the key/value.
    :type key: str
    :param value: The value in the key/value pair.
    :type value: Any
    :param model: The model to look in. Defaults to the default model.
    :type model: Model
    :param type: When creating a new attribute, this is the recorded value type.
      Default is str.
    :type type: str
    :param restriction: When creating a new attribute, this is the inheritance
      restriction on the attribute. Legal values are "VAR", "VAR_DEFAULTED", 
      "CONST", "CONST_TYPEOVERRIDE", "TYPENAME". Default is "VAR" 
    :type restriction: str
    '''
    pass
    
  class _Set_attribute(Command): 
    def __init__(self, object:GraphObject, key:str, value:Any, /, 
                 model:Model|None=None, type:str|None=None, restriction:str|None=None):
      '''
      Set the attribute of an object.
      
      :param object: The object who's attribute is to be set.
      :type object: GraphObject
      :param key: The key in the key/value.
      :type key: str
      :param value: The value in the key/value pair.
      :type value: Any
      :param model: The model to look in. Defaults to the default model.
      :type model: Model
      :param type: When creating a new attribute, this is the recorded value type.
        Default is str.
      :type type: str
      :param restriction: When creating a new attribute, this is the inheritance
        restriction on the attribute. Legal values are "VAR", "VAR_DEFAULTED", 
        "CONST", "CONST_TYPEOVERRIDE", "TYPENAME". Default is "VAR" 
      :type restriction: str
      '''
      super().__init__("set attribute")
      if type is not None: # check the type string to make sure it represents an actual type
        typ = getClass(type) if type is not None else None
        assert typ is not None
      else:
        typ = str
      self.typ = typ 
      self.object:GraphObject = object
      self.key:str = key
      self.value:Any = value
      if typ is not None and isinstance(value, str):
        self.value = typ(value)
      if self.object._getSuperAttr(self.key) is None and restriction is None:
        restriction = "VAR"
      self.restrictionStr = restriction
      self.restriction:Restriction|None = Restriction.fromstring(restriction) if restriction is not None else None

      localObj = self.object.getLocalAttr(key)
      self.oldAttrValue = None if localObj is None else localObj

    @override
    def do(self):
      super().do()
      if self.object._getSuperAttr(self.key) is None:
        self.object.setAttr(self.key, Attribute(self.value, self.typ, restriction=self.restriction))
        self.created = True
      else:
        self.object[self.key] = self.value
        self.created = False
  
    @override
    def undo(self):
      super().undo()
      if self.oldAttrValue is None:
        del self.object[self.key]
      else:
        self.object.setAttr(self.key, self.oldAttrValue)
      
    @override
    def delete(self):
      super().delete()
      self.object = None # type: ignore[assignment]
      self.value = None

    @override
    def __str__(self):
      return f'{super().__str__()} {self.object.getPRef().tostring()} {self.key} {self.value}{(" --type="+self.typ.__name__) if self.typ is not None else ""}{(" --restriction="+self.restrictionStr) if self.restrictionStr is not None else ""}'

      
  def delete_attribute(self, object:GraphObject|None, key:str, /, \
                    model:Optional[Model]=None) -> Any|None:
    '''
    Set the attribute of a *GraphObject*.
    
    :param object: The object who's attribute is to be set.
    :type object: GraphObject
    :param key: The key in the key/value.
    :type key: str
    :param model: The model to look in. Defaults to the default model.
    :type model: Model
    '''
    pass
    
  class _Delete_attribute(Command): 
    def __init__(self, object:GraphObject, key:str, /, 
                 model:Model|None=None):
      '''
      Set the attribute of an object.
      
      :param object: The object who's attribute is to be set.
      :type object: GraphObject
      :param key: The key in the key/value.
      :type key: str
      :param model: The model to look in. Defaults to the default model.
      :type model: Model
      '''
      super().__init__("set attribute")
      self.object:GraphObject = object
      self.key:str = key
      self.localObj = self.object.getLocalAttr(key)

    @override
    def do(self):
      super().do()
      del self.object[self.key]
  
    @override
    def undo(self):
      super().undo()
      self.object[self.key] = self.localObj
      
    @override
    def delete(self):
      super().delete()
      self.object = None # type: ignore[assignment]
      self.localObj = None

    @override
    def __str__(self):
      return f'{super().__str__()} {self.object.getPRef().tostring()} {self.key}'

      
      
  def exit(self):
    '''
    Quit the program.
    '''
    raise SystemExit("sn")
  
  
  _QUERY_SPECIAL_SYMBOLS = ['?', '*']
  
  def query(self, objects:list[str|GraphObject], /, model:Optional[Model]=None, astree:bool=False, keepdups:bool=False):
    '''
    Query a model in one <fetch>, <type>, or <relation> expression forms.
    
      - <obj>                     # "echos" the referenced object (str->GraphObject)
      - <type> <obj>              # <obj> isa <type>
      - <obj1> <relation> <obj2>  # <obj1> is related to <obj2> by <relation> 
      
    where any of the of the  tokens may be an reference to an object or one of
    the query tokens "?" or "*".  If a query token does not appear in the
    expression, it will return a boolean answer.  If one query token appears in
    the expression, the answer will be a list of objects that satisfy the 
    expression. If two query tokens appear in the expression, the answer will 
    be a list of pairs (tuples) that satisfy the expression. 
    
    The difference between "?" and "*" only applies to <type> queries: "?" 
    returns results only one level deep (eg: direct parents), while "*" returns
    transitive and reflexive results (eg: self and all ancestors).
    
    Examples:
    
      - query person    -> Node("person", #19, <type>)
      - query person ?  -> Node("Fred", #21, <individual>), Node("Jane", #23, <individual>)
      - query ? Jane    -> Node("person", #19, <type>)
      - query * Jane    -> Node("Jane", #23, <individual>), Node("person", #19, <type>),
                           Node("node", #6, <type>), GraphObject("top", #1, <type>)
      - query Jane isa person -> True
      - query ? isa person -> Node("Fred", #21, <individual>), Node("Jane", #23, <individual>)
    
    :param objects: The objects in the expression (up to 3)
    :type objects: list[str|GraphObject]
    :param astree: If True return a list result of <type> expression as a "tree list".
    :type astree: bool
    :param keepdups: If True do not remove duplicates from a list result of <type> expression.
    :type keepdups: bool
    :param model: The model to look in. Defaults to the default model.
    :type model: Model
    '''
    if isinstance(objects, str):
      objects = [objects]
    assert isinstance(objects, list), f'query(): argument 1 must be a list. Got type {type(objects)}: "{objects}"'
    if not len(objects) in [1, 2, 3]:
      raise ValueError(f'An expression must contain either 1, 2 or 3 elements. Got {len(objects)}: "{objects}"')
    
    nSyms:int = 0
    nObjs:int = 0
    expLen = len(objects)
    for i in range(len(objects)):
      if objects[i] in self._QUERY_SPECIAL_SYMBOLS:
        nSyms += 1
      else:
        nObjs += 1
        obj = objects[i]
        if isinstance(obj, str):
          go:GraphObject|PRDb[GraphObject]
          if i == 1 and expLen == 3: # second argument must a type in a relational expression
            go = GORef.eval(obj, model, filtr=lambda o: o.isType()) #type: ignore[call-overload, attr-defined]
          elif i == 0 and expLen == 2: # first argument must be a type in a type expression
            go = GORef.eval(obj, model, filtr=lambda o: o.isType()) #type: ignore[call-overload, attr-defined]
          else:
            go = GORef.eval(obj, model) #type: ignore[call-overload]
          assert isinstance(go, GraphObject)
          objects[i] = go
        if not (isinstance(objects[i], GraphObject) or isinstance(objects[i], Model) and expLen==1):
          raise ValueError(f"Expected a GraphObject at position {i+1}. Got {objects[i]}.")
    if nObjs == 0:
      raise SyntaxError(f'Expected at least one GraphObject in expression.')
    
    # an "echo" expression...
    if expLen == 1:
      return objects[0]
    
    # a "type" expression...
    if expLen == 2:
      t = objects[0]
      obj = objects[1]
      assert t in self._QUERY_SPECIAL_SYMBOLS or isinstance(t, GraphObject) and t.isType(), \
          "The first object in a type expression must be a type."
      if t == "*":
        assert isinstance(obj, GraphObject)
        return obj.isa(asTree=astree, rmDups=not keepdups)
      if t == '?':
        assert isinstance(obj, GraphObject)
        return obj.getParents()
      if obj == "*":
        assert isinstance(t, GraphObject)
        if astree:
          ret:list = [t]
          ret.append(t.getDescendants(asTree=astree, rmDups=not keepdups, model=model))
          return ret
        else:
          return [t]+t.getDescendants(asTree=astree, rmDups=not keepdups, model=model) 
      if obj == '?':
        assert isinstance(t, GraphObject)
        return t.getChildren()
      assert isinstance(obj, GraphObject)
      assert isinstance(t, GraphObject)
      return obj.isa(t)
    
    # a "relational" expression...
    if expLen == 3:
      obj1 = objects[0]
      rel = objects[1]
      obj2 = objects[2]
      assert rel in self._QUERY_SPECIAL_SYMBOLS or isinstance(rel, Relation) and (rel.isType()), "The second object in a relational expression must be a relation type."
      case = (1 if obj1 not in self._QUERY_SPECIAL_SYMBOLS else 0) + \
             (2 if rel  not in self._QUERY_SPECIAL_SYMBOLS else 0) + \
             (4 if obj2 not in self._QUERY_SPECIAL_SYMBOLS else 0)
      assert case != 0 # this would be the case of all ? or *.
      if case == 1: # obj1 ? ? : obj1 only is given
        assert isinstance(obj1, GraphObject)
        return obj1.isRelatedTo()
      if case == 2: # ? rel ? : rel only is given
        assert isinstance(rel, Relation)
        instances = [r for r in rel.getDescendants(model) if r.isIndividual()]
        return [(r.src, r.dst) for r in instances]
      if case == 3: # obj1 rel ? : obj2 is the only var
        assert isinstance(obj1, GraphObject)
        assert isinstance(rel, Relation)
        return obj1.isRelatedTo(rel)
      if case == 4: # ? ? obj2 : obj2 only is given
        assert isinstance(obj2, GraphObject)
        return obj2.isRelatedFrom()
      if case == 5: # obj1 ? obj2: rel is the only var
        assert isinstance(obj1, GraphObject)
        return [r for r,o in obj1.isRelatedTo() if o is obj2]
      if case == 6: # ? rel obj2 : obj1 is the only var
        assert isinstance(obj2, GraphObject)
        assert isinstance(rel, Relation)
        return obj2.isRelatedFrom(rel)
      if case == 7: # obj1 rel obj2 : No vars, boolean response
        assert isinstance(obj1, GraphObject)
        assert isinstance(rel, Relation)
        assert isinstance(obj2, GraphObject)
        return obj1.isRelatedTo(rel, obj2)
      raise SyntaxError(f'Unrecognized relational expression: {objects}')
      
    
    
  # This is just a signature -- the behaviour is in class _New_node.
  def assert_(self, objects:list[str|GraphObject], /, type:bool=False, model:Optional[Model]=None):
    '''
    Assert a predicate in the model; ie: create an object of some type,
    add a parent type to an object, or create a new relation between objects.
    
    Examples:
    
      - assert node person --type    -> Node("person", #19, <type>) 
                        {and IsaInstance("isa", #20, <individual>, #19 -> #?)}
                        Create a type "person"
      - assert person fred           -> Node("fred", #21, <individual>) 
                        {and IsaInstance("isa", #20, <individual>, #21 -> #19)}
                        Create an instance of person, "fred", assuming object
                        "fred does not already exist. If "fred" doesn exist,
                        then only the IsaInstance is created.
      - assert transitive sibling --type -> Relation("sibling", #23, <type>, #? -> #?)
                        {and IsaInstance("isa", #24, <individual>, #23 -> #?)}
                        Create a relation type "sibling" inheriting from "transitive".
      - assert symmetric sibling     -> Relation("sibling", #23, <type>, #? -> #?) (same one) 
                        {and IsaInstance("isa", #25, <individual>, #23 -> #?)}
                        Create only the IsaInstance since "sibling" already exists.
      - assert person sibling person -> Relation("sibling", #23, <type>, #19 -> #?19) (same one)
                        Since "sibling" exists and person is a type, modify the src and dst
                        both to be "person".
      - assert person gorge          -> Node("gorge", #26, <individual)
                        {and IsaInstance("isa", #27, <individual>, #26 -> #19)}
      - assert fred sibling gorge    -> Relation("sibling", #28, <individual>, #21 -> #26) 
                        {and IsaInstance("isa", #28, <individual>, #28 -> #23)}
                        Create a new relation instance "sibling" between "fred" and "gorge".
    
    '''
    pass

  class _Assert_(Command):
    def __init__(self, objects:list[str|GraphObject], /, type:bool=False, model:Optional[Model]=None):
      '''
      Assert a predicate in the model; ie: create an object of some type,
      add a parent type to an object, or create a new relation between objects.
      
      
      '''
      def eval_(s:str|GraphObject, m:Model, filtr:Callable=lambda o:True) -> GraphObject:
        if isinstance(s, GraphObject):
          return s
        ret = GORef.eval(s, m, filtr)
        assert isinstance(ret, GraphObject)
        return ret
      
      # param checking...
      assert model is not None, "There is no Model specified."
      super().__init__("assert_")
      self.model:Model = model
    
      assert isinstance(objects, list), "assert(): argument 1 must be a list."
      expLen = len(objects)
      if not expLen in [2, 3]:
        raise ValueError(f"An expression must contain either 2 or 3 elements. Got {len(objects)}.")
      
      self.typ:GraphObject|None = None
      self.obj1:GraphObject|None = None
      self.obj2:GraphObject|None = None
      self.objName:str|None = None
      self.typeParam = type
      self.rel:Relation|None = None
      self.oldSrcDst:tuple[GraphObject|None, GraphObject|None]|None = None
      if expLen == 2: # type expression: self.type
        # obj1&~objName -> isa; 
        # ~obj1&objName -> create&isa
        self.typ = eval_(objects[0], model, filtr=lambda o: o.isType())
        try:
          self.obj1 = eval_(objects[1], model, filtr=lambda o: isinstance(o, GraphObject))
        except:
          assert isinstance(objects[1], str)
          self.obj1 = None
          self.objName = objects[1]
      elif expLen == 3: # relational expression: rel must be a relation type
        # obj1.isType()&pbj2.isType() -> modify rel type src&dst
        # obj1.isIndividual()&obj2.isIndividual() -> create new rel instance 
        self.obj1 = eval_(objects[0], model)
        self.rel = eval_(objects[1], model, filtr=lambda o: isinstance(o, Relation) and o.isType()) #type: ignore[assignment]
        assert isinstance(self.rel, Relation)
        self.obj2 = eval_(objects[2], model)
      assert (self.rel is None) ^ (self.typ is None) # xor
      self.artifact:GraphObject|None = None
      
    @override
    def do(self) -> GraphObject:
      super().do()
      if self.artifact is not None: # this is a redo: just reconnect the object
        self.artifact._reconnect()
        return self.artifact

      # type expression
      if self.typ:
        t = type(self.typ)
        if self.obj1: # we are just adding a parent type to an existing object
          self.artifact = IsaIndividual(self.model, self.obj1, self.typ)
          return self.obj1
        else: # we are creating a new object.
          assert self.objName
          if t is Node:
            self.artifact = Node(self.model, [self.typ], individual=not self.typeParam, name=self.objName)
            return self.artifact
          if t is Relation:
            if not self.typeParam:
              raise SyntaxError('Create an individual relation using a relation expression, "<src> <relation-type> <dst>')  
            self.artifact = Relation(self.model, [self.typ], individual=not self.typeParam, name=self.objName)
            return self.artifact
          if t is Collection:
            self.artifact = Collection(self.model, [self.typ], individual=not self.typeParam, name=self.objName)
            return self.artifact
            
      
      # relation expression
      elif self.rel:
        assert self.obj1
        assert self.obj2
        if self.obj1.isType(): # modify the relations type's src and dst
          if self.obj2.isType():
            self.oldSrcDst = (self.rel._src, self.rel._dst)
            self.artifact = self.rel
            self.rel.connect(self.obj1, self.obj2)
            return self.artifact
          else:
            raise SyntaxError(f'First and third arguments must both be type or both be individuals.')
        else: 
          self.artifact = Relation(self.model, [self.rel], individual=not self.typeParam, src=self.obj1, dst=self.obj2)
          return self.artifact
        
      raise SyntaxError(f'Unrecognized expression')
        
    @override
    def undo(self):
      assert self.artifact is not None
      super().undo()
      if self.oldSrcDst:
        assert isinstance(self.rel, Relation)
        self.rel.connect(self.oldSrcDst[0], self.oldSrcDst[1])
      else:
        self.artifact._disconnect()
      return self.artifact
      
      
    @override
    def delete(self):
      super().delete()
      self.model = None #type: ignore[assignment]
      self.obj1 = None
      self.obj2 = None
      self.rel = None
      self.typ = None
      
    @override
    def __str__(self):
      def getName(obj:GraphObject|None):
        return obj.name if obj is not None else "None"
      if self.rel is None:
        return f'{super().__str__()} "{getName(self.typ)}" "{getName(self.artifact)}"{" --type" if self.typeParam else ""} --model="{self.model.url}"'
      else:
        return f'{super().__str__()} "{getName(self.obj1)}" "{getName(self.rel)}" "{getName(self.obj2)}"{" --type" if self.typeParam else ""} --model="{self.model.url}"'

  def new_model(self, url:str, /, mode:str="w") -> Model:
    '''
    Create a new model.
    
    :param url: The url (or file name) in which to create the model. Must not already exist.
    :type url: str
    :param mode: The mode in which to open the model ("r" or "w"). Default "w".
    :type mode: str
    :returns: The newly created model
    :rtype: Model
    '''
    url = fixURL(url, extension=".xml", replaceExt=None, mode=mode)[0]
    if not isValidURL(url):
      raise ValueError(f'Malformed URL: "{url}"')
    if url in PRDb.AllDBs:
      raise DuplicateNameError(f'A DB with name "{url}" already exists in memory.')
    if urlExists(url):
      raise FileExistsError(f'URL already exists. Use PRDb.getDB("{url}") to open it.')
    return Model(url, mode=mode)

  # This is just a signature -- the behaviour is in class _New_node.
  def new_node(self, parent:Node|list[Node], /, name:Optional[str]=None, individual:bool=False, type:bool=False, model:Model|None=None):
    '''
    Create a new Node object.
    
    It is an error for both *individual* and *type* to be true.  If both are 
    false, the object will be an *individual*.

    :param parent: The direct parent or parents of the object from which they will inherit attributes.
    :type parent: GraphObject
    :param name: The name of the new node. It need not be unique in the model, but that
      may lead to ambiguities in searching for it my name, so uniqueness would be good...
      If the name is not given, it will inherit it's name from the first parent if it's a type
      and if it's an individual, the name will be blank.
    :type name: Optional[str]
    :param individual: If True, this will be an individual, otherwise it will be a type. Defaults to True.
    :type individual: bool
    :param type: If True, this will be a type, otherwise it will be a individual. Defaults to True.
    :type type: bool
    :param model: The Model in which to create the object. Default: the current default model.
    :type model: Model
    '''
    pass
    
  class _New_node(Command):
    def __init__(self, parent:GraphObject|list[GraphObject], /, name:Optional[str]=None, individual:bool=False, type:bool=False, model:Optional[Model]=None):
      '''
      Create a new Node object.
      
      It is an error for both *individual* and *type* to be present.  If both are 
      missing the object will be an *individual*.

      :param parent: The direct parent or parents of the object from which they will inherit attributes.
      :type parent: GraphObject
      :param name: The name of the new node. It need not be unique in the model, but that
        may lead to ambiguities in searching for it my name, so uniqueness would be good...
        If the name is not given, it will inherit it's name from the first parent if it's a type
        and if it's an individual, the name will be blank.
      :type name: Optional[str]
      :param individual: If True, this will be an individual, otherwise it will be a type. Defaults to True.
      :type individual: bool
      :param type: If True, this will be a type, otherwise it will be a individual. Defaults to True.
      :type type: bool
      :param model: The Model in which to create the object. Default: the current default model.
      :type model: Model
      '''
      # param checking...
      assert model is not None, "There is no Model specified."
      assert not (type and individual), "An GraphObject cannot be both an individual and a type."
      parents:list[GraphObject] = [parent] if not isinstance(parent, list) else parent
      self.parents:list[Node] = []
      for p in parents:
        assert isinstance(p, Node)
        self.parents.append(p)
        
      super().__init__("new node")
      self.individual:bool = not type
      self.nodeName:Optional[str] = name
      self.model:Model = model
      self.node:Optional[Node] = None
    
    @override
    def do(self) -> Node:
      super().do()
      with Subject.ChangeMgr(self.model, later=True) as cm:
        if self.node is None:
          self.node = Node(self.model, self.parents, self.individual, self.nodeName)
        else:
          self.node._reconnect()
      return self.node
  
    @override
    def undo(self):
      assert self.node is not None
      super().undo()
      with Subject.ChangeMgr(self.model, later=True) as cm:
        self.node._disconnect()
      return self.node
      
    @override
    def delete(self):
      super().delete()
      self.model = None #type: ignore[assignment]
      self.node = None
      
    @override
    def __str__(self):
      name = f' --name={self.nodeName}' if self.nodeName is not None else ''
      #TODO: the 'self.parents' part is a bit of cluge as the python version takes a list and the argparse version only takes an singleton.
      return f'{super().__str__()} {self.parents[0]}{name} --individual={self.individual} --model="{self.model.url}"'

  # This is just a signature -- the behaviour is in class _New_node.
  def remove(self, object:GraphObject):
    '''
    Delete a *GraphObject*.
    
    :param object: The *GraphObject* to delete.
    :type object: GraphObject
    '''
    pass
    
  class _Remove(Command):
    def __init__(self, object:GraphObject):
      '''
      Delete a object from it's model.
      
      :param object: The object to delete.
      :type object: GraphObject
      '''
      # param checking...
      super().__init__("remove")
      self.object:GraphObject = object
    
    @override
    def do(self):
      super().do()
      self.object._disconnect()
  
    @override
    def undo(self):
      super().undo()
      self.object._reconnect()
      
    @override
    def delete(self):
      super().delete()
      self.object = None #type: ignore[assignment]
      
    @override
    def __str__(self):
      return f'{super().__str__()} {self.object.getPRef().tostring()}'

  # This is just a signature -- the behaviour is in class _New_node.
  def new_relation(self, parent:GraphObject|list[GraphObject], /, 
                 name:Optional[str]=None, 
                 individual:bool=False, type:bool=False, 
                 destination:GraphObject|None=None, source:GraphObject|None=None, 
                 model:Optional[Model]=None):
    '''
    Create a new Relation object between other objects.
    
    It is an error for both *individual* and *type* to be true.  If both are 
    false, the object will be an *individual*.

    :param parent: The direct parent or parents of the object from which they will inherit attributes.
    :type parent: GraphObject|list[GraphObject]
    :param name: The name of the new node. It need not be unique in the model, but that
      may lead to ambiguities in searching for it my name, so uniqueness would be good...
      If the name is not given, it will inherit it's name from the first parent if it's a type
      and if it's an individual, the name will be blank.
    :type name: Optional[str]
    :param individual: If True, this will be an individual, otherwise it will be a type. Defaults to True.
    :type individual: bool
    :param type: If True, this will be a type, otherwise it will be a individual. Defaults to True.
    :type type: bool
    :param destination: The object at the destination side of the relation. By default it 
      will inherit from the first parent.
    :type destination: GraphObject|None
    :param source: The object at the source side of the relation. By default it 
      will inherit from the first parent.
    :type source: GraphObject|None
    :param model: The Model in which to create the object. Default: the current default model.
    :type model: Model
    '''
    pass
    
  class _New_relation(Command):
    def __init__(self, parent:GraphObject|list[GraphObject], /, 
                 name:Optional[str]=None, 
                 individual:bool=False, type:bool=False, 
                 destination:GraphObject|None=None, source:GraphObject|None=None, 
                 model:Optional[Model]=None):
      '''
      Create a new Relation object between other objects.
      
      It is an error for both *individual* and *type* to be present.  If both are 
      missing the object will be an *individual*.

      :param parent: The direct parent or parents of the object from which they will inherit attributes.
      :type parent: GraphObject [GraphObject ...]
      :param name: The name of the new relation. It need not be unique in the model, but that
        may lead to ambiguities in searching for it my name, so uniqueness would be good...
        If the name is not given, it will inherit it's name from the first parent if it's a type
        and if it's an individual, the name will be blank.
      :type name: Optional[str]
      :param individual: If True, this will be an individual, otherwise it will be a type. Defaults to True.
      :type individual: bool
      :param type: If True, this will be a type, otherwise it will be a individual. Defaults to True.
      :type type: bool
      :param destination: The object at the destination side of the relation. By default it 
        will inherit from the first parent.
      :type destination: GraphObject
      :param source: The object at the source side of the relation. By default it 
        will inherit from the first parent.
      :type source: GraphObject
      :param model: The Model in which to create the object. Default: the current default model.
      :type model: Model
      '''
      # param checking...
      assert model is not None, "There is no Model specified."
      assert not (type and individual), "An GraphObject cannot be both an individual and a type."
      parents:list[GraphObject] = [parent] if not isinstance(parent, list) else parent
      self.parents:list[Relation] = []
      for p in parents:
        assert isinstance(p, Relation), f'Expected Relation, got type {p.__class__.__name__}.'
        self.parents.append(p)
      if len(self.parents) > 1 and self.model.ISA in self.parents:
        raise TypeError("Multiple parents cannot include the ISA relation.")
        
        
      super().__init__("new relation")
      assert model is not None
      self.individual:bool = not type
      self.nodeName:Optional[str] = name
      self.source:GraphObject|None = source
      self.destination:GraphObject|None = destination
      self.model:Model = model
      self.relation:Optional[Relation] = None
    
    @override
    def do(self) -> Relation:
      super().do()
      if self.relation is None:
        if len(self.parents) ==1 and self.parents[0] is self.model.ISA:
          self.relation = IsaIndividual(self.model, self.source, self.destination)
        else:
          self.relation = Relation(self.model, self.parents, self.source, self.destination, self.individual, self.nodeName)
      else:
        self.relation._reconnect()
      return self.relation
  
    @override
    def undo(self):
      assert self.relation is not None
      super().undo()
      self.relation._disconnect()
      return self.relation
      
    @override
    def delete(self):
      super().delete()
      self.model = None #type: ignore[assignment]
      self.relation = None
      
    @override
    def __str__(self):
      name = f' --name={self.nodeName}' if self.nodeName is not None else ''
      #TODO: the 'self.parents' part is a bit of cluge as the python version takes a list and the argparse version only takes an singleton.
      return f'{super().__str__()} {self.parents[0]}{name} --individual={self.individual} --model="{self.model.url}"'

if __name__ == '__main__':
  def printx(s:str):
    print(f'> {s}')
    print(eval(s))
  m = Model("temp.xml")
  logger.setLevel(logging.DEBUG)
  context = ModelContext(m)
  printx('context.show(model=m, detail=True)')
  printx('context.show(detail=True)')
  printx('context.parser.parseLine("show --detail")')
  printx('context.parser.parseLine("show")')
  # try:
  m = Model("y.xml")
  # except Exception as ex:
  #   m = Model.getDB("y.xml")
  m.save()
  printx('context.default("model", m) # m == y.xml')
  print('-------- should be y.xml now -------------')
  printx('context.show(detail=True)')
  printx('context.parser.parseLine("undo")')
  print('-------- should be temp.xml now -------------')
  #printx("context.parser.parseLine('help default')")
  printx('context.show()')
  printx('context.parser.parseLine("default model y.xml")')
  print('-------- should be y.xml now -------------')
  printx('context.parser.parseLine("show")')
  #print(context.parser.parseLine("help"))
  print("-------")
  #printx('context.show("#1")')
  printx('context.parser.parseLine("show 1 --d")')
  printx('context.show(detail=True)')
    