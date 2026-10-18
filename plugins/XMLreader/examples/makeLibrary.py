'''
Make a library of *n* made-up books as an XML file, for trying *XMLreader* on
something bigger than *books.xml*:

  python3.14 makeLibrary.py n file.xml

Each book has an id, a kind (novel, textbook, ...: XMLreader makes each a
subtype of book), a year and a language, a title, one of 50 authors, and two
chapters. (library25.xml and library200.xml were made with this.)

Created on Oct 3, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import sys

KINDS = ("novel", "textbook", "poetry", "biography")

def makeLibrary(n:int) -> str:
  '''
  :param n: How many books.
  :returns: The library, as XML.
  '''
  lines = ['<?xml version="1.0"?>', "<library>"]
  for i in range(n):
    lines += [f'  <book id="b{i}" kind="{KINDS[i % len(KINDS)]}" year="{1900 + i % 100}" lang="en">',
              f'    <title>Title {i}</title>',
              f'    <author name="A{i % 50}"/>',
              '    <chapter n="1"/>',
              '    <chapter n="2"/>',
              '  </book>']
  lines.append("</library>")
  return "\n".join(lines) + "\n"

if __name__ == "__main__":
  if len(sys.argv) != 3:
    sys.exit(__doc__)
  with open(sys.argv[2], "w", encoding="utf-8") as f:
    f.write(makeLibrary(int(sys.argv[1])))
