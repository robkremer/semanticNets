#################################################################################
# (c) Copyright 2024-2025, Rob Kremer, MIT open source license.                 #
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
from abc import abstractmethod, ABC
from typing import Any, Callable, Optional, Union, NamedTuple
#import xml.etree.ElementTree as ET
#from xml.etree.ElementTree import Element, ElementTree
from dataclasses import dataclass, field
from util.utils import getFullClassName, getClassFromFullyQualifiedName,\
  fixURL

import os
import urllib.request
from urllib.parse import ParseResult

#TODO: write the tests for tostring() and fromstring()

 
'''
Created on Mar 20, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>

'''

VERSION = "1.0"
TAG_WRAPPER = "persistentObjects"
TAG_VERSION = "version"
TAG_OBJECT = "object"
TAG_PROPERTY = "property"
ATTR_NAME = "_name_"
ATTR_TYPE = "_type_"
ATTR_VALUE = "_value_"

class ParamInfo(NamedTuple):
  name: str # the name of the parameter
  typ: type # the type of the parameter
  writeMethod: Callable[[Any], Any] # a function taking 1 "self" parameter and returning a str.
  
@dataclass
class InstantiationInfo:
  def __post_init__(self):
    '''
    Check that no name is duplicated in and between the any of args lists. 
    '''
    names:list[str] = []
    for args in (self.conArgs, self.conKWArgs, self.postconArgs, self.finalArgs):
      for pinfo in args:
        if pinfo.name in names:
          raise NameError(f'Duplicate name "{pinfo.name}".')
        names.append(pinfo.name)
  class_:type
  conArgs:list[ParamInfo] # param types
  conKWArgs:list[ParamInfo]
  postconArgs:list[ParamInfo] = field(default_factory=list)
  postconMethod:Optional[Callable] = None
  finalArgs:list[ParamInfo] = field(default_factory=list)
  finalMethod:Optional[Callable] = None
  
  @property
  def className(self):
    return getFullClassName(self.class_)
  
class PersistentObject:
  @classmethod
  @abstractmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    raise NotImplementedError("Abstract method PersistentObject.getInstantiationInfo() not implemented.")
    

def getInstantiationInfo(className:str) -> InstantiationInfo:
  '''
  :param className: The name of a *PersistentObject* subclass. 
  :type className: str   
  :returns: the *InstantiationInfo* structure for *className*.
  :rtype: InstantiationInfo
  :raises TypeError: if the class cannot be found or  
  
  Look up the *InstantiationInfo* structure for *className* and return it.
  '''
  cls:Optional[type] = getClassFromFullyQualifiedName(className)
  if cls is None:
    raise TypeError(f'Cannot find type "{className}".')
  if not issubclass(cls, PersistentObject):
    raise TypeError(f'Class "{className}" is not a subtype of PersisentObject.')
  return cls.getInstantiationInfo()


class PersistenceStrategy[ReaderType](ABC):
  '''
  A Strategy pattern class designed to save objects in a manner that allows for
  multiple storage formats (eg: XML, JSON, etc). This class proposes to support
  build-in data types: *int, float, bool, str, list, dict, tuple, set*, as
  well as any (properly constructed) user-defined subclass of *PersistentObject*.
  
  **Users** of the subclasses  
  '''

  PersistentTypes = Union[PersistentObject, int, float, bool, str, list, dict, tuple, set]
  PersistentTypesInAttrs = (int, float, bool, str)
  PersistentTypesInSubs = (PersistentObject, list, dict, tuple, set)
    
  def __init__(self):
    '''
    Create an object from a byte array.
    '''
    self.finalMethodsList:list[Callable] = []
    
  @abstractmethod
  def defaultExtension(self) -> str:
    raise NotImplementedError("Call on abstract method PersistenceStrategy.defaultExtension()")
    
  @abstractmethod
  def _encodeObject(self, obj:PersistentTypes) -> ReaderType:
    '''
    :param obj: 
    :type obj: PersistentObject   
    :returns: 
    :rtype: ReaderType
    :raises NotImlementedError: If the subclass failed to implement this
      method. 
    '''
    raise NotImplementedError("Call on abstract method PersistenceStrategy._encodeObject()")
  
  @abstractmethod
  def _decodeObject(self, readerObj:ReaderType) -> PersistentTypes:
    '''
    :param readerObj: An ReaderType object suitable for the subclass 
    :type readerObj: ReaderType   
    :returns: An object read from *readerObj*.
    :rtype: Any
    :raises NotImlementedError: If the subclass failed to implement this
      method.
    
    Converts a *ReaderType* object to an object. 
    '''
    raise NotImplementedError("Call on abstract method PersistenceStrategy._decodeObject()")
  
  def _wrap(self, elem:ReaderType) -> ReaderType:
    '''
    Subclasses should override
    '''
    return elem
    
  def _unwrap(self, root:ReaderType) -> ReaderType:
    '''
    Subclasses should override
    '''
    return root
    
  @abstractmethod
  def tostring(self, obj:PersistentTypes) -> str:
    """
    Return the data as a strategy-specific formatted string.
  
    :param obj: The object to serialise and returned.
    :type obj: PersistentTypes
    :returns: The serialized object as a string.
    :rtype: str
    """
    raise NotImplementedError("Call on abstract method PersistenceStrategy.tostring()")
    
  @abstractmethod
  def fromstring(self, string:str) -> PersistentTypes:
    """
    Return an object made from a strategy-specific formatted string.
  
    :param string: The string to interpret.
    :type string: str
    :returns: The object interpreted from *string*.
    :rtype: PersistentTypes
    """
    raise NotImplementedError("Call on abstract method PersistenceStrategy.fromstring()")
  
  def write(self, url:str, obj:PersistentTypes, replaceExt:Optional[bool]=True) -> None:
    """
    Write an the data to a URL.
  
    For ``file:`` URLs the data is written directly to the local filesystem path.
    For all other schemes (e.g. ``http:``, ``https:``) the XML is uploaded via
    :func:`urllib.request.urlopen` as an HTTP PUT request with content-type
    ``application/xml``.
  
    :param url: The destination URL. Use ``file:///absolute/path`` or
      ``file://relative/path`` for local files.
    :type url: str
    :param obj: The object to serialise and write.
    :type obj: PersistentTypes
    :param replaceExt: If True, (the default) any extension will be replace with
      the default extension; if False, the default will extension will be 
      appended to the path if it's not already there; if None, nothing will
      be done to the path.
    :type replaceExt: Optional[bool]
    :returns: None
    :rtype: None
    :raises ValueError: If *url* is an empty string.
    :raises FileNotFoundError: If the parent directory of a ``file:`` URL path
      does not exist.
    :raises urllib.error.URLError: If a remote URL cannot be reached.
  
    Usage::
  
      >>> tree = ET.parse("data.xml")
      >>> write("file:///tmp/output.xml", tree)
      >>> write("https://example.com/api/document", tree)
    """
    parsedUrl:ParseResult
    url, parsedUrl = fixURL(url, replaceExt=replaceExt, mode="w", extension=self.defaultExtension())
    
    if parsedUrl.scheme == "file":
      localPath: str = parsedUrl.netloc + parsedUrl.path
      absolutePath: str = os.path.abspath(localPath)
      with open(absolutePath, "w", encoding="utf-8") as f:
        f.write(self.tostring(obj))
      return
  
    buf:bytes = self.tostring(obj).encode("utf-8")
    request:urllib.request.Request = urllib.request.Request(
      url,
      data=buf,
      method="PUT",
      headers={"Content-Type": "application/xml; charset=utf-8"},
    )
    with urllib.request.urlopen(request):
      pass
    
  def read(self, url:str, replaceExt:bool=True) -> PersistentTypes:
    '''
    :param buf:  
    :type buf: bytes   
    :returns: An object read from *buf* 
    :rtype: Any
    :raises NotImlementedError: If the subclass failed to implement one of its
      required methods.
    
    Converts a byte array to an object using *_decodeObject()* and 
    *_speicializeBytes()*. 
    '''
    self.finalMethodsList = []
    parsedUrl:ParseResult
    url, parsedUrl = fixURL(url, replaceExt=replaceExt, mode="r", extension=self.defaultExtension())
  
    scheme:str = parsedUrl.scheme.lower() if parsedUrl.scheme else "file"
  
    if scheme == "file":
      localPath:str = parsedUrl.path if parsedUrl.path else url
      with open(localPath, "r", encoding="utf-8") as f:
        contents:str = f.read()      
    elif scheme in ("http", "https"):
      with urllib.request.urlopen(url) as response:
        rawBytes: bytes = response.read()
      contents = rawBytes.decode(encoding="utf-8")
    else:
      raise ValueError(f"Unsupported URL scheme: '{scheme}'. Use 'file', 'http', or 'https'.")    
    
    ret = self.fromstring(contents)
    
    for finalMethod in self.finalMethodsList:
      finalMethod()
    self.finalMethodsList = []
    
    return ret
  
  

