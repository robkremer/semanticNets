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
from typing import Any, override, cast, Union
from util.utils import getFullClassName, getClassFromFullyQualifiedName
from json import loads, dumps
from sn.persistence import PersistenceStrategy, ParamInfo, TAG_OBJECT,\
  PersistentObject, InstantiationInfo, getInstantiationInfo,\
  TAG_WRAPPER, TAG_VERSION, VERSION

JSONtypes = Union[dict, list, int, float, bool, str]
TAG_FILETYPE = "_filetype_"
TAG_ROOT = "_root_"
TAG_TUPLE = "_tuple_"
TAG_SET = "_set_"


class JSONPersistenceStrategy(PersistenceStrategy[JSONtypes]):
  
  @override
  def _encodeObject(self, obj:PersistenceStrategy.PersistentTypes) -> JSONtypes:
    
    def encodeDictKey(key:Any) -> str:
      if type(key) is str:
        return key
      return f'!!{dumps(self._encodeObject(key))}'
    
    def getAttrs(obj:PersistenceStrategy.PersistentTypes, 
                        pinfos:list[ParamInfo]
                        ) -> list[tuple[str, JSONtypes]]:
      'Return the list of XML attributes and the list of XML subelements (children).'
      attrs:list[tuple[str, JSONtypes]] = []
      for pinfo in pinfos:
        typ:type = pinfo.typ
        name:str = pinfo.name
        writeMethod = pinfo.writeMethod
        if issubclass(typ, PersistentObject):
          attrs.append((name, self._encodeObject(writeMethod(obj))))
        elif typ in (int, float, bool, str):
          attrs.append((name, writeMethod(obj)))
        elif typ is list:
          elemlist = []
          for i in writeMethod(obj):
            elemlist.append(self._encodeObject(i))
          attrs.append((name, elemlist))
        elif typ is tuple:
          attrs.append((name, {TAG_TUPLE: self._encodeObject(list(writeMethod(obj)))}))
        elif typ is set:
          attrs.append((name, {TAG_SET: self._encodeObject(list(writeMethod(obj)))}))
        elif typ is dict:
          elemdict = dict()
          for k,v in writeMethod(obj).items():
            elemdict[encodeDictKey(k)] = self._encodeObject(v)
          attrs.append((name, elemdict))
        else:
          raise NotImplementedError(f'JSON encoding not implemented for type {getFullClassName(typ)}')
      return attrs
    
    if isinstance(obj, PersistentObject):
      elem:dict[JSONtypes,JSONtypes] = {TAG_OBJECT: getFullClassName(type(obj))}
      info:InstantiationInfo = obj.getInstantiationInfo()
      for args in (info.conArgs, info.conKWArgs, info.postconArgs, info.finalArgs):
        attrs = getAttrs(obj, args)
        for k,v in attrs:
          elem[k] = v
      return elem
    elif type(obj) in (int,float,str,bool):
      return cast(JSONtypes, obj)
    elif type(obj) is list:
      elemlist:list[JSONtypes] = []
      for i in obj:
        elemlist.append(self._encodeObject(i))
      return elemlist
    elif type(obj) is tuple:
      return self._encodeObject({TAG_TUPLE: list(obj)})
    elif type(obj) is set:
      return self._encodeObject({TAG_SET: list(obj)})
    elif type(obj) is dict:
      elem = dict()
      for k,v in obj.items():
        elem[encodeDictKey(k)] = self._encodeObject(v)
      return elem
    else:
      raise TypeError(f'Unsupported type: "{obj.__class__.__name__}".') 
    
  @override
  def _decodeObject(self, elem:JSONtypes) -> PersistenceStrategy.PersistentTypes:
    
    def decodeDictKey(key:str) -> PersistenceStrategy.PersistentTypes:
      if not key.startswith("!!"):
        return key
      k = key[2:]
      return self._decodeObject(loads(k))
    
    def getArgs(desc:list[ParamInfo]) -> list[tuple[str, PersistenceStrategy.PersistentTypes]]: 
      ret:list[tuple[str, PersistenceStrategy.PersistentTypes]] = []
      for p in desc:
        pinfo:ParamInfo = p
        ret.append((pinfo.name, self._decodeObject(elem[pinfo.name])))
      return ret
    
    if type(elem) in [int, float, bool, str]:
      return elem
    if type(elem) is dict: # could be dict or an object
      if TAG_OBJECT in elem: # it's a user-defined object
        className = elem[TAG_OBJECT]
        cls = getClassFromFullyQualifiedName(className)
        if cls is None:
          raise TypeError(f'Could not find type "{className}"')
        if issubclass(cls, PersistentObject):
          info:InstantiationInfo = getInstantiationInfo(className)
          stuff = getArgs(info.conArgs)
          args:list = [x[1] for x in stuff] # convert from pairs to list of 2nds
          stuff = getArgs(info.conKWArgs)
          kwargs:dict[str,Any] = dict(stuff)
          ret = cls(*args, **kwargs)
          if info.postconMethod is not None:
            stuff = getArgs(info.postconArgs)
            info.postconMethod(ret, **dict(stuff))
          if info.finalMethod is not None:
            stuff = getArgs(info.finalArgs)
            self.finalMethodsList.append(lambda 
                                            obj=ret, 
                                            method=info.finalMethod, 
                                            kwargs=dict(stuff): 
                                              method(obj, **kwargs))
          return ret
        else:
          raise NotImplementedError(f'Not supported: User-defined classes that are not subclasses of {str(PersistentObject)}')
      else: # it's an ordinary dict, or set or a tuple
        if len(elem) == 1: # sets and tuples are single-key dicts
          if TAG_TUPLE in elem:
            return tuple(self._decodeObject(elem[TAG_TUPLE]))
          if TAG_SET in elem:
            return set(self._decodeObject(elem[TAG_SET]))
        retDict:dict[Any,Any] = dict()
        for k,v in elem.items():
          retDict[decodeDictKey(k)] = self._decodeObject(v)
        return retDict
        
    elif isinstance(elem, list):
      retList:list[PersistenceStrategy.PersistentTypes] = []
      for i in elem:
        retList.append(self._decodeObject(i))
      return retList 
    
    raise NotImplementedError(f'Not supported: type {str(type(elem))}')
            
  @override
  def defaultExtension(self) -> str:
    return ".json"
    
  @override
  def _wrap(self, elem:JSONtypes) -> JSONtypes:
    return {TAG_FILETYPE: TAG_WRAPPER,
            TAG_VERSION  : VERSION,
            TAG_ROOT     : elem
           }
  
  @override
  def _unwrap(self, top:JSONtypes) -> JSONtypes:
    if not isinstance(top, dict) or TAG_FILETYPE not in top or top[TAG_FILETYPE] != TAG_WRAPPER:
      try:
        appendment =  f' but got "{top[TAG_FILETYPE]}"' # type: ignore[index, call-overload]
      except:
        appendment = ""
      raise TypeError(f'Data does not seem to be JSON {TAG_WRAPPER} data: Expected {TAG_FILETYPE} of "{TAG_WRAPPER}"{appendment}.')
    self.readingVersion = top.get(TAG_VERSION, "<unknown>")
    
    ret = top.get(TAG_ROOT, None)
    if ret is None:
      raise SyntaxError(f'Malfored XML doc: Could not find root object in "{TAG_ROOT}".')
    return ret
    
  def tostring(self, obj:PersistenceStrategy.PersistentTypes) -> str:
    """
    Return the data as a strategy-specific formatted string.
    
    :param obj: The object to serialise and returned.
    :type obj: PersistentTypes
    :returns: The serialized object as a string.
    :rtype: str
    """
    return dumps(self._wrap(self._encodeObject(obj)), indent=2)

  def fromstring(self, string:str) -> PersistenceStrategy.PersistentTypes:
    """
    Return an object made from a strategy-specific formatted string.
    
    :param string: The string to interpret.
    :type string: str
    :returns: The object interpreted from *string*.
    :rtype: PersistentTypes
    """
    return self._decodeObject(self._unwrap(loads(string)))
    