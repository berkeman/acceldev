############################################################################
#                                                                          #
# Copyright (c) 2017 eBay Inc.                                             #
# Modifications copyright (c) 2018-2019 Carl Drougge                       #
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

# a few things that differ between python2 and python3

from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import sys
try:
	from setproctitle import setproctitle as _setproctitle
except ImportError:
	def _setproctitle(title): pass

if sys.version_info[0] == 2:
	PY2 = True
	PY3 = False
	import __builtin__ as builtins
	import cPickle as pickle
	from urllib import quote_plus, unquote_plus, urlencode
	from urllib2 import urlopen, Request, URLError, HTTPError
	from itertools import izip, imap, ifilter
	from Queue import Queue, Full as QueueFull, Empty as QueueEmpty
	from types import NoneType
	str_types = (str, unicode,)
	int_types = (int, long,)
	num_types = (int, float, long,)
	unicode = builtins.unicode
	long = builtins.long
	def iterkeys(d):
		return d.iterkeys()
	def itervalues(d):
		return d.itervalues()
	def iteritems(d):
		return d.iteritems()
	from io import open
	def getarglist(func):
		from inspect import getargspec
		return getargspec(func).args
else:
	PY2 = False
	PY3 = True
	import builtins
	import pickle
	from urllib.parse import quote_plus, unquote_plus
	from urllib.request import urlopen, Request
	from urllib.error import URLError, HTTPError
	izip = zip
	imap = map
	ifilter = filter
	from queue import Queue, Full as QueueFull, Empty as QueueEmpty
	NoneType = type(None)
	str_types = (str,)
	int_types = (int,)
	num_types = (int, float,)
	unicode = str
	open = builtins.open
	long = int
	def iterkeys(d):
		return iter(d.keys())
	def itervalues(d):
		return iter(d.values())
	def iteritems(d):
		return iter(d.items())
	def urlencode(query):
		from urllib.parse import urlencode
		return urlencode(query).encode('utf-8')
	def getarglist(func):
		from inspect import getfullargspec
		return getfullargspec(func).args

def first_value(d):
	return next(itervalues(d) if isinstance(d, dict) else iter(d))

def uni(s):
	if s is None:
		return None
	if isinstance(s, bytes):
		try:
			return s.decode('utf-8')
		except UnicodeDecodeError:
			return s.decode('iso-8859-1')
	return unicode(s)

# This is used in the method launcher to set different titles for each
# phase/slice. You can use it in the method to override that if you want.
def setproctitle(title):
	import g
	if hasattr(g, 'METHOD'):
		title = '%s %s (%s)' % (g.JOBID, uni(title), g.METHOD,)
	else:
		title = '%s %s' % (g.JOBID, uni(title),)
	if PY2:
		title = title.encode('utf-8')
	_setproctitle(title)
