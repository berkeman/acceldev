############################################################################
#                                                                          #
# Copyright (c) 2017 eBay Inc.                                             #
#                                                                          #
# Licensed under the Apache License, Version 2.0 (the "License");          #
# you may not use this file except in compliance with the License.         #
# You may obtain a copy of the License at                                  #
#                                                                          #
#  http://www.apache.org/licenses/LICENSE-2.0                              #
#                                                                          #
# Unless required by applicable law or agreed to in writing, software      #
# distributed under the License is distributed on an "AS IS" BASIS,        #
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. #
# See the License for the specific language governing permissions and      #
# limitations under the License.                                           #
#                                                                          #
############################################################################

from __future__ import print_function
from __future__ import division

import gzutil

assert gzutil.version >= (2, 10, 0) and gzutil.version[0] == 2, gzutil.version

from accelerator.compat import PY3

type2iter = {
	'number'  : gzutil.GzNumber,
	'float64' : gzutil.GzFloat64,
	'float32' : gzutil.GzFloat32,
	'int64'   : gzutil.GzInt64,
	'int32'   : gzutil.GzInt32,
	'bits64'  : gzutil.GzBits64,
	'bits32'  : gzutil.GzBits32,
	'bool'    : gzutil.GzBool,
	'datetime': gzutil.GzDateTime,
	'date'    : gzutil.GzDate,
	'time'    : gzutil.GzTime,
	'bytes'   : gzutil.GzBytes,
	'ascii'   : gzutil.GzAscii,
	'unicode' : gzutil.GzUnicode,
# These are for compatibility with older datasets, don't use them.
	'_v2_bytes'  : gzutil.GzBytesLines,
	'_v2_ascii'  : gzutil.GzAsciiLines,
	'_v2_unicode': gzutil.GzUnicodeLines,
}

from ujson import loads
class GzJson(object):
	def __init__(self, *a, **kw):
		if PY3:
			self.fh = gzutil.GzUnicode(*a, **kw)
		else:
			self.fh = gzutil.GzBytes(*a, **kw)
	def __next__(self):
		return loads(next(self.fh))
	next = __next__
	def close(self):
		self.fh.close()
	def __iter__(self):
		return self
	def __enter__(self):
		return self
	def __exit__(self, type, value, traceback):
		self.close()
type2iter['json'] = GzJson

# Just like the base Lines-types we have a compat version of json
class _V2_GzJson(GzJson):
	def __init__(self, *a, **kw):
		if PY3:
			self.fh = gzutil.GzUnicodeLines(*a, **kw)
		else:
			self.fh = gzutil.GzBytesLines(*a, **kw)
type2iter['_v2_json'] = _V2_GzJson

def typed_reader(typename):
	if typename not in type2iter:
		raise ValueError("Unknown reader for type %s" % (typename,))
	return type2iter[typename]
