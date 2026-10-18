#################################################################################
# (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
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
'''
A first run -- no *SN_FOLDER* yet -- still saves the preferences at exit
(see *sn.savePrefsIfChanged()*).

Created on Oct 18, 2026

@author: robkremer
'''
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import sn


class Test(unittest.TestCase):

  def test0100freshHome(self):
    with tempfile.TemporaryDirectory() as home:
      env = dict(os.environ, HOME=home, PYTHONPATH=os.pathsep.join(sys.path))
      result = subprocess.run([sys.executable, "-c", "import sn"], env=env,
                              capture_output=True, text=True, timeout=120)
      self.assertNotIn("PermissionError", result.stderr)
      self.assertTrue((Path(home)/f".{sn.SHORT_NAME}"/"prefs.xml").is_file(), result.stderr)


if __name__ == "__main__":
  unittest.main()
