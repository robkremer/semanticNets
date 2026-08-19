from __future__ import annotations

from typing import Iterator, ItemsView, KeysView, ValuesView, Optional, Union
from abc import abstractmethod
from weakref import ref
from util.utils import openUrl, urlExists
import xml.etree.ElementTree as ET

class DuplicateNameError(Exception):
  """Raised when a name lookup matches more than one PRObject."""

class MalformedIDError(Exception):
  """Raised a PReference is syntactically incorrect."""

class PReference:
  def __init__(self, text:str):
    '''
    :param text: A string in the form of <URL>#<id>, where <id> can be an int,
      a string with no spaces or a quoted string.
      
    Creates a reference to a PRObject without actually trying to instantiate the
    PRObject or checking on it's existance. The instantiate the object, use
    a call on this object.
    '''
    parts:tuple[str, Union[int,str]] = self._isValidID(text) # throws if not valid
    self.text:str = text
    self.dbName:str = parts[0]
    self.id_:Union[int,str] = parts[1]
    self.obj:Optional[PRObject] = None
    
  def __call__(self) -> PRObject:
    '''
    :return: the resolved *PRObject*.
    :raises LookupError: if the reference cannot be resolved.
    '''
    if self.obj is None:
      db = PRDb.getDB(self.dbName)
      self.obj = db[self.id_]
    return self.obj
    
  def _isValidID(self, text:str) -> tuple[str, Union[int,str]]:
    parts:list[str] = self.text.split('#')
    if len(parts) != 2:
      raise MalformedIDError(f'No "#" found in id "{self.text}')
    url:str = parts[0]
    id_:str = parts[1]
    retID:Union[int,str] = -1
    if url not in PRDb._db and not urlExists(url):
      raise FileNotFoundError(f'No URL "{self.text}" exists')
    try:
      retID = int(id_)
    except:
      if id_.startswith('"') and id_.endswith('"'):
        retID = id_[1:-1]
      else:
        for c in id_: 
          if c.isspace():
            raise MalformedIDError(f'ID "{text}" object part must be an int, or non-space string, or a quoted string.')
        retID = id_
    return url, retID

class PRObject:
  """An object with an immutable integer ID and a mutable name."""

  def __init__(self, db: PRDb) -> None:
    if not isinstance(db, PRDb):
      raise TypeError(f"db must be an PRDb, got {type(id).__name__}")
    self._db = ref(db) # weak reference as the db will maintain references to this object
    self._id: int = db._register(self)

  @property
  def id(self) -> int:
    return self._id

  @property
  def db(self) -> Optional[PRDb]:
    return self._db()

  @property
  @abstractmethod
  def name(self) -> str:
    pass
  
  @name.setter
  @abstractmethod
  def name(self, newName:str):
    pass
    
  def __repr__(self) -> str:
    return f"PRObject(ID={self.id!r}, name={self.name!r})"

  def __eq__(self, other: object) -> bool:
    if isinstance(other, PRObject):
      return self.id == other._PObject.id and self.name == other.name  # type: ignore[attr-defined]
    return NotImplemented


class PRDb:  # type: ignore[type-arg]
  """
  A dict-like object whose keys are restricted to int and values to PRObject.

  __getitem__() and related lookup methods accept either:
    - an int  -> direct key lookup by ID
    - a str   -> lookup by PRObject.name (raises DuplicateNameError if ambiguous)
    
  METHODS NOT IMPLEMENTED:
  
    - __setitem__() (index assignment) is NOT implemented.  Instead, the constructor
        of PRObject calls *PRDb._register()* to obtain an id and insert itself into
        the *PRDb*.
    - update()
  """
  
  AllDBs:dict[str, PRDb] = dict()
  
  @classmethod
  def getDB(cls, name:str):
    '''
    :param name: The name of the db as a file name or a URL.
    :returns: The DB read from disk or from the web.
    :raises FileNotFoundError: If the db cannot be instantiated.

    Either return the DB from memory or attempt to read it from disk or 
    from the web.
    '''
    if name in PRDb.AllDBs:
      return PRDb.AllDBs[name]
    return cls._read(name)
      
  @classmethod
  def _read(cls, url:str) -> PRDb:
    '''
    :param url: The URL to fetch. May use any scheme supported by
      :mod:`urllib.request`, plus the ``file:`` protocol for local filesystem
      paths.
    :type url: str
    :returns: Raw byte content of the resource, suitable for passing directly to
      an XML parser (e.g. :func:`xml.etree.ElementTree._fromstring` or
      :class:`lxml.etree.XMLParser`).
    :rtype: bytes
    :raises ValueError: If *url* is an empty string.
    :raises FileNotFoundError: If a ``file:`` URL points to a path that does not
      exist.
    :raises urllib.error.URLError: If a remote URL cannot be reached.
    
    Read the DB from disk or from the web and instantiate it.
    Subclasses should implement this method to actually do the read; this 
    version merely raises the exception.
    '''
    xmlBytes:bytes = openUrl(url)
    return ET._fromstring(xmlBytes)
  
  def __init__(self, name:str):
    if name in self.AllDBs:
      raise DuplicateNameError(f'A DB with name "{name}" already exists.')
    self._db:dict[int, PRObject] = dict()
    self.nextID:int = 1
    self.AllDBs[name] = self

  # ── Write-side enforcement ────────────────────────────────────────────────

  def _register(self, value: PRObject) -> int:
    '''
    :param value: The PRObject to be added to this DB.
    :return: A new (locally) unique id for this object.
    
    Generate a (locally) unique id for this object and add it the this DB.
    
    The method is private, but is used in the constructor of *PRObject*.
    '''
    if not isinstance(value, PRObject):
      raise TypeError(f"Values must be PRObject, got {type(value).__name__}")
    key = self.nextID
    self.nextID += 1
    self._db[key] = value
    return key

  # ── Name-resolution helper ────────────────────────────────────────────────

  def _resolve(self, key: int | str) -> int:
    """
    Return the integer key for *key*.

    - int  -> returned as-is (existence check deferred to caller)
    - str  -> scanned for a matching .name; DuplicateNameError if >1 match
    """
    if isinstance(key, int):
      return key
    if isinstance(key, str):
      matches: list[int] = [
        k for k, v in self._db.items() if v.name == key
      ]
      if len(matches) > 1:
        raise DuplicateNameError(
          f"Name {key!r} matches multiple entries: {matches}"
        )
      if len(matches) == 0:
        raise KeyError(key)
      return matches[0]
    raise TypeError(
      f"Key must be int or str, got {type(key).__name__}"
    )

  # ── Read-side overrides ───────────────────────────────────────────────────

  def __getitem__(self, key: int | str) -> PRObject:
    return self._db.__getitem__(self._resolve(key))

  def __contains__(self, key: object) -> bool:
    if isinstance(key, str):
      try:
        self._resolve(key)
        return True
      except KeyError:
        return False
    if isinstance(key, int):
      return self._db.__contains__(key)
    return False

  def get(
    self,
    key: int | str,
    default: PRObject | None = None,
  ) -> PRObject | None:
    try:
      return self[key]
    except KeyError:
      return default

  def __iter__(self) -> Iterator[int]:
    return self._db.__iter__()

  def keys(self) -> KeysView[int]:
    return self._db.keys()

  def values(self) -> ValuesView[PRObject]:
    return self._db.values()

  def items(self) -> ItemsView[int, PRObject]:
    return self._db.items()

  # ── Representation ────────────────────────────────────────────────────────

  def __repr__(self) -> str:
    inner: str = ", ".join(f"{k!r}: {v!r}" for k, v in self.items())
    return f"PRDb({{{inner}}})"
  
  def __str__(self) -> str:
    return f'PRDb(<{len(self._db)} items>)'


# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
  
  class CPObject(PRObject): # concrete PRObject
    def __init__(self, db:PRDb, name:str):
      super().__init__(db)
      self._name:str = name
      
    @property
    def name(self) -> str:
      return self._name

    @name.setter
    def name(self, name:str):
      self._name = name
      
  db: PRDb = PRDb("db")
  

  print("=== PRObject ===\n")

  a: PRObject = CPObject(db, "Alice")
  b: PRObject = CPObject(db, "Bob")
  c: PRObject = CPObject(db, "Carol")

  print(a, b, c)

  # ID is immutable
  try:
    a.id = 99  # type: ignore[misc]
  except AttributeError as e:
    print(f"Immutability enforced: {e}")

  # name is mutable
  a.name = "Alicia"
  print(f"Renamed: {a}")

  print("\n=== PRDb ===\n")

  print("DB:", db, "; repr():", repr(db))

  # Lookup by ID
  print("\nLookup by ID:")
  print("  db[2]          →", db[2])

  # Lookup by name
  print("\nLookup by name:")
  print("  db['Carol']    →", db["Carol"])

  # get() by name
  print("  db.get('Bob')  →", db.get("Bob"))
  print("  db.get('Zara') →", db.get("Zara", None))

  # contains
  print("\nContains:")
  print("  1 in db        →", 1 in db)
  print("  'Bob' in db    →", "Bob" in db)
  print("  'Zara' in db   →", "Zara" in db)

  # Duplicate name triggers DuplicateNameError
  print("\nDuplicate name test:")
  CPObject(db, "Bob")  # second "Bob" at index 4
  try:
    db["Bob"]
  except DuplicateNameError as e:
    print(f"  DuplicateNameError: {e}")

  # Type enforcement
  print("\nType enforcement:")
  try:
    db[1.4] # type: ignore[index]
  except TypeError as e:
    print(f"  Bad key type:   {e}")
  try:
    db[5] = db[4]  # type: ignore[index]
  except TypeError as e:
    print(f"  Bad value type: {e}")
