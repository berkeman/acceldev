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

from __future__ import division
from __future__ import absolute_import

from resource import getpagesize
from os import unlink
from mmap import mmap, PROT_READ
from shutil import copyfileobj
from struct import Struct
import itertools

from accelerator.compat import NoneType, unicode, imap, itervalues, PY2

from accelerator.extras import OptionEnum, DotDict
from accelerator.gzwrite import typed_writer, typed_reader
from accelerator.sourcedata import type2iter
from . import dataset_type

depend_extra = (dataset_type,)

description = r'''
Convert one or more columns in a dataset from bytes/ascii/unicode to any type.
Also rehashes if you type the hashlabel, or specify a new hashlabel.
'''

# Without filter_bad the method fails when a value fails to convert and
# doesn't have a default. With filter_bad the value is filtered out
# together with all other values on the same line.
#
# With filter_bad, when rehashing or when typing a chain a new dataset is
# produced, so any columns not in column2type that are not of a bytes-like
# type will be discarded. You can set discard_untyped to discard all
# unspecified columns, or set it to False to get an error if any columns
# were not preservable (except columns renamed over).

TYPENAME = OptionEnum(dataset_type.convfuncs.keys())

options = {
	'column2type'               : {'COLNAME': TYPENAME},
	'hashlabel'                 : str, # leave as None to inherit hashlabel, set to '' to not have a hashlabel
	'defaults'                  : {}, # {'COLNAME': value}, unspecified -> method fails on unconvertible unless filter_bad
	'rename'                    : {}, # {'OLDNAME': 'NEWNAME'} doesn't shadow OLDNAME. (Other COLNAMEs use NEWNAME.)
	'caption'                   : 'typed dataset',
	'discard_untyped'           : bool, # Make unconverted columns inaccessible ("new" dataset)
	'filter_bad'                : False, # Implies discard_untyped
	'numeric_comma'             : False, # floats as "3,14"
	'length'                    : -1, # Go back at most this many datasets. You almost always want -1 (which goes until previous.source)
	'as_chain'                  : False, # one dataset per slice if rehashing (avoids rewriting at the end)
	'compression'               : 6,     # gzip level
}

datasets = ('source', 'previous',)


byteslike_types = ('bytes', 'ascii', 'unicode',)

cstuff = dataset_type.init()

def prepare(job, slices):
	assert 1 <= options.compression <= 9
	cstuff.backend.init()
	d = datasets.source
	chain = d.chain(stop_ds={datasets.previous: 'source'}, length=options.length)
	if len(chain) == 1:
		filename = d.filename
	else:
		filename = None
	lines = [sum(ds.lines[sliceno] for ds in chain) for sliceno in range(slices)]
	columns = {}
	column2type = dict(options.column2type)
	rev_rename = {}
	for k, v in options.rename.items():
		if k in d.columns and (v in column2type or options.discard_untyped is not True):
			if v in rev_rename:
				raise Exception('Both column %r and column %r rename to %r' % (rev_rename[v], k, v,))
			rev_rename[v] = k
	for colname, coltype in column2type.items():
		orig_colname = rev_rename.get(colname, colname)
		for ds in chain:
			if orig_colname not in ds.columns:
				raise Exception("Dataset %s doesn't have a column named %r (has %r)" % (ds, orig_colname, set(ds.columns),))
			if ds.columns[orig_colname].type not in byteslike_types:
				raise Exception("Dataset %s column %r is type %s, must be one of %r" % (ds, orig_colname, ds.columns[orig_colname].type, byteslike_types,))
		coltype = coltype.split(':', 1)[0]
		columns[colname] = dataset_type.typerename.get(coltype, coltype)
	if options.hashlabel is None:
		hashlabel = options.rename.get(d.hashlabel, d.hashlabel)
		if hashlabel in columns:
			if rev_rename.get(hashlabel, hashlabel) != d.hashlabel:
				# hashlabel gets overwritten
				hashlabel = None
		rehashing = (hashlabel in columns)
		hashlabel_override = False
	else:
		hashlabel = options.hashlabel or None
		rehashing = bool(hashlabel)
		hashlabel_override = True
	if (options.filter_bad or rehashing or len(chain) > 1) and not options.discard_untyped:
		untyped_columns = set(d.columns)
		for ds in chain:
			untyped_columns &= set(ds.columns)
		orig_columns = set(rev_rename.get(n, n) for n in columns)
		untyped_columns -= set(columns) # anything renamed over is irrelevant
		untyped_columns -= orig_columns
		if options.discard_untyped is False:
			missing = set(d.columns) - untyped_columns - set(columns) - orig_columns
			if missing:
				raise Exception('discard_untyped is False, but not all columns in %s exist in the whole chain (missing %r)' % (d, missing,))
		cand2type = {}
		unkeepable = set()
		for colname in sorted(untyped_columns):
			target_colname = options.rename.get(colname, colname)
			if target_colname in cand2type:
				continue
			ts = set(ds.columns[colname].type for ds in chain)
			if len(ts) == 1:
				t = ts.pop()
			else:
				# We could be a bit more generous and use bytes for other
				# workable combinations, or even unicode for {ascii, unicode}.
				t = 'BAD'
			if t in byteslike_types:
				cand2type[target_colname] = t
			else:
				unkeepable.add(colname)
		if options.discard_untyped is False:
			assert not unkeepable, 'The following columns had unkeepable or varying types: %r' % (unkeepable,)
		else:
			columns.update(cand2type)
			column2type.update((k, 'unicode:utf-8' if v == 'unicode' else v) for k, v in cand2type.items())
	if options.filter_bad or rehashing or options.discard_untyped or len(chain) > 1:
		parent = None
	else:
		parent = datasets.source
	if hashlabel and hashlabel not in columns:
		if options.hashlabel:
			raise Exception("Can't rehash on untyped column %r." % (hashlabel,))
		hashlabel = None # it gets inherited from the parent if we're keeping it.
		hashlabel_override = False
	dws = []
	if rehashing:
		previous = datasets.previous
		for sliceno in range(slices):
			if options.as_chain and sliceno == slices - 1:
				name = 'default'
			else:
				name = str(sliceno)
			dw = job.datasetwriter(
				columns=columns,
				caption='%s (from slice %d)' % (options.caption, sliceno,),
				hashlabel=hashlabel,
				filename=filename,
				previous=previous,
				meta_only=True,
				name=name,
				for_single_slice=sliceno,
			)
			previous = dw
			dws.append(dw)
	if rehashing and options.as_chain:
		dw = None
	else:
		dw = job.datasetwriter(
			columns=columns,
			caption=options.caption,
			hashlabel=hashlabel,
			hashlabel_override=hashlabel_override,
			filename=filename,
			parent=parent,
			previous=datasets.previous,
			meta_only=True,
		)
	return dw, dws, lines, chain, column2type


def map_init(vars, name, z='badmap_size'):
	if not vars.badmap_size:
		pagesize = getpagesize()
		line_count = vars.lines[vars.sliceno]
		vars.badmap_size = (line_count // 8 // pagesize + 1) * pagesize
		vars.slicemap_size = (line_count * 2 // pagesize + 1) * pagesize
	fh = open(name, 'w+b')
	vars.map_fhs.append(fh)
	fh.truncate(vars[z])
	return fh.fileno()


def analysis(sliceno, slices, prepare_res):
	if options.numeric_comma:
		try_locales = [
			'da_DK', 'nb_NO', 'nn_NO', 'sv_SE', 'fi_FI',
			'en_ZA', 'es_ES', 'es_MX', 'fr_FR', 'ru_RU',
			'de_DE', 'nl_NL', 'it_IT',
		]
		for localename in try_locales:
			localename = localename.encode('ascii')
			if not cstuff.backend.numeric_comma(localename):
				break
			if not cstuff.backend.numeric_comma(localename + b'.UTF-8'):
				break
		else:
			raise Exception("Failed to enable numeric_comma, please install at least one of the following locales: " + " ".join(try_locales))
	dw, dws, lines, chain, column2type = prepare_res
	if dws:
		dw = dws[sliceno]
		rehashing = True
	else:
		rehashing = False
	vars = DotDict(
		sliceno=sliceno,
		slices=slices,
		known_line_count=0,
		badmap_size=0,
		badmap_fd=-1,
		slicemap_size=0,
		slicemap_fd=-1,
		map_fhs=[],
		res_bad_count={},
		res_default_count={},
		res_minmax={},
		first_lap=True,
		rehashing=rehashing,
		hash_lines=None,
		dw=dw,
		chain=chain,
		lines=lines,
		column2type=column2type,
		rev_rename={v: k for k, v in options.rename.items() if k in datasets.source.columns and v in column2type},
	)
	if options.filter_bad:
		vars.badmap_fd = map_init(vars, 'badmap%d' % (sliceno,))
		bad_count, default_count, minmax = analysis_lap(vars)
		if sum(sum(c) for c in itervalues(bad_count)):
			vars.first_lap = False
			vars.res_bad_count = {}
			final_bad_count, default_count, minmax = analysis_lap(vars)
			final_bad_count = [max(c) for c in zip(*final_bad_count.values())]
		else:
			final_bad_count = [0] * slices
	else:
		bad_count, default_count, minmax = analysis_lap(vars)
		final_bad_count = [0] * slices
	for fh in vars.map_fhs:
		fh.close()
	if rehashing:
		unlink('slicemap%d' % (sliceno,))
	return bad_count, final_bad_count, default_count, minmax, vars.hash_lines


# In python3 indexing into bytes gives integers (b'a'[0] == 97),
# this gives the same behaviour on python2. (For use with mmap.)
class IntegerBytesWrapper(object):
	def __init__(self, inner):
		self.inner = inner
	def close(self):
		self.inner.close()
	def __getitem__(self, key):
		return ord(self.inner[key])
	def __setitem__(self, key, value):
		self.inner[key] = chr(value)

# But even in python3 we can only get int8 support for free,
# and slicemap needs int16.
class Int16BytesWrapper(object):
	_s = Struct('=H')
	def __init__(self, inner):
		self.inner = inner
	def close(self):
		self.inner.close()
	def __getitem__(self, key):
		return self._s.unpack_from(self.inner, key * 2)[0]
	def __setitem__(self, key, value):
		self._s.pack_into(self.inner, key * 2, value)
	def __iter__(self):
		if PY2:
			def it():
				for o in range(len(self.inner) // 2):
					yield self[o]
		else:
			def it():
				for v, in self._s.iter_unpack(self.inner):
					yield v
		return it()


def analysis_lap(vars):
	if vars.rehashing:
		if vars.first_lap:
			out_fn = 'hashtmp.%d' % (vars.sliceno,)
			colname = vars.rev_rename.get(vars.dw.hashlabel, vars.dw.hashlabel)
			coltype = vars.column2type[options.rename.get(colname, colname)]
			vars.rehashing = False
			real_coltype = one_column(vars, colname, coltype, [out_fn], True)
			vars.rehashing = True
			assert vars.res_bad_count[colname] == [0] # imlicitly has a default
			vars.slicemap_fd = map_init(vars, 'slicemap%d' % (vars.sliceno,), 'slicemap_size')
			slicemap = mmap(vars.slicemap_fd, vars.slicemap_size)
			slicemap = Int16BytesWrapper(slicemap)
			hash = typed_writer(real_coltype).hash
			slices = vars.slices
			vars.hash_lines = hash_lines = [0] * slices
			for ix, value in enumerate(typed_reader(real_coltype)(out_fn)):
				dest_slice = hash(value) % slices
				slicemap[ix] = dest_slice
				hash_lines[dest_slice] += 1
			unlink(out_fn)
	for colname, coltype in vars.column2type.items():
		if vars.rehashing:
			out_fns = [vars.dw.column_filename(colname, sliceno=s) for s in range(vars.slices)]
		else:
			out_fns = [vars.dw.column_filename(colname)]
		one_column(vars, vars.rev_rename.get(colname, colname), coltype, out_fns)
	return vars.res_bad_count, vars.res_default_count, vars.res_minmax


def one_column(vars, colname, coltype, out_fns, for_hasher=False):
	if for_hasher:
		record_bad = skip_bad = False
	elif vars.first_lap:
		record_bad = options.filter_bad
		skip_bad = False
	else:
		record_bad = 0
		skip_bad = options.filter_bad
	minmax_fn = 'minmax%d' % (vars.sliceno,)

	fmt = fmt_b = None
	if coltype in dataset_type.convfuncs:
		shorttype = coltype
		_, cfunc, pyfunc = dataset_type.convfuncs[coltype]
	else:
		shorttype, fmt = coltype.split(':', 1)
		_, cfunc, pyfunc = dataset_type.convfuncs[shorttype + ':*']
	if cfunc:
		cfunc = shorttype.replace(':', '_')
	if pyfunc:
		tmp = pyfunc(coltype)
		if callable(tmp):
			pyfunc = tmp
			cfunc = None
		else:
			pyfunc = None
			cfunc, fmt, fmt_b = tmp
	if coltype == 'number':
		cfunc = 'number'
	elif coltype == 'number:int':
		coltype = 'number'
		cfunc = 'number'
		fmt = "int"
	assert cfunc or pyfunc, coltype + " didn't have cfunc or pyfunc"
	coltype = shorttype
	in_fns = []
	offsets = []
	max_counts = []
	for d in vars.chain:
		assert colname in d.columns, '%s not in %s' % (colname, d,)
		assert d.columns[colname].type in byteslike_types, '%s has bad type in %s' % (colname, d,)
		in_fns.append(d.column_filename(colname, vars.sliceno))
		if d.columns[colname].offsets:
			offsets.append(d.columns[colname].offsets[vars.sliceno])
			max_counts.append(d.lines[vars.sliceno])
		else:
			offsets.append(0)
			max_counts.append(-1)
	if cfunc:
		default_value = options.defaults.get(colname, cstuff.NULL)
		if for_hasher and default_value is cstuff.NULL:
			if coltype.startswith('bits'):
				# No None-support.
				default_value = '0'
			else:
				default_value = None
		default_len = 0
		if default_value is None:
			default_value = cstuff.NULL
			default_value_is_None = True
		else:
			default_value_is_None = False
			if default_value != cstuff.NULL:
				if isinstance(default_value, unicode):
					default_value = default_value.encode("utf-8")
				default_len = len(default_value)
		c = getattr(cstuff.backend, 'convert_column_' + cfunc)
		if vars.rehashing:
			c_slices = vars.slices
		else:
			c_slices = 1
		bad_count = cstuff.mk_uint64(c_slices)
		default_count = cstuff.mk_uint64(c_slices)
		gzip_mode = "wb%d" % (options.compression,)
		res = c(*cstuff.bytesargs(in_fns, len(in_fns), out_fns, gzip_mode, minmax_fn, default_value, default_len, default_value_is_None, fmt, fmt_b, record_bad, skip_bad, vars.badmap_fd, vars.badmap_size, c_slices, vars.slicemap_fd, vars.slicemap_size, bad_count, default_count, offsets, max_counts))
		assert not res, 'Failed to convert ' + colname
		vars.res_bad_count[colname] = list(bad_count)
		vars.res_default_count[colname] = sum(default_count)
		coltype = coltype.split(':', 1)[0]
		real_coltype = dataset_type.typerename.get(coltype, coltype)
		with type2iter[real_coltype](minmax_fn) as it:
			vars.res_minmax[colname] = list(it)
		unlink(minmax_fn)
	else:
		# python func
		if for_hasher:
			raise Exception("Can't hash on column of type %s." % (coltype,))
		nodefault = object()
		if colname in options.defaults:
			default_value = options.defaults[colname]
			if default_value is not None:
				if isinstance(default_value, unicode):
					default_value = default_value.encode('utf-8')
				default_value = pyfunc(default_value)
		else:
			default_value = nodefault
		if options.filter_bad:
			badmap = mmap(vars.badmap_fd, vars.badmap_size)
			if PY2:
				badmap = IntegerBytesWrapper(badmap)
		if vars.rehashing:
			slicemap = mmap(vars.slicemap_fd, vars.slicemap_size)
			slicemap = Int16BytesWrapper(slicemap)
			bad_count = [0] * vars.slices
		else:
			bad_count = [0]
			chosen_slice = 0
		default_count = 0
		dont_minmax_types = {'bytes', 'ascii', 'unicode', 'json'}
		real_coltype = dataset_type.typerename.get(coltype, coltype)
		do_minmax = real_coltype not in dont_minmax_types
		fhs = [typed_writer(real_coltype)(fn) for fn in out_fns]
		write = fhs[0].write
		col_min = col_max = None
		it = itertools.chain.from_iterable(d._column_iterator(vars.sliceno, colname, _type='bytes') for d in vars.chain)
		for ix, v in enumerate(it):
			if vars.rehashing:
				chosen_slice = slicemap[ix]
				write = fhs[chosen_slice].write
			if skip_bad:
				if badmap[ix // 8] & (1 << (ix % 8)):
					bad_count[chosen_slice] += 1
					continue
			try:
				v = pyfunc(v)
			except ValueError:
				if default_value is not nodefault:
					v = default_value
					default_count += 1
				elif record_bad:
					bad_count[chosen_slice] += 1
					bv = badmap[ix // 8]
					badmap[ix // 8] = bv | (1 << (ix % 8))
					continue
				else:
					raise Exception("Invalid value %r with no default in %s" % (v, colname,))
			if do_minmax and not isinstance(v, NoneType):
				if col_min is None:
					col_min = col_max = v
				if v < col_min: col_min = v
				if v > col_max: col_max = v
			write(v)
		for fh in fhs:
			fh.close()
		if vars.rehashing:
			slicemap.close()
		if options.filter_bad:
			badmap.close()
		vars.res_bad_count[colname] = bad_count
		vars.res_default_count[colname] = default_count
		vars.res_minmax[colname] = [col_min, col_max]
	return real_coltype

def synthesis(slices, analysis_res, prepare_res):
	dw, dws, lines, _, _ = prepare_res
	analysis_res = list(analysis_res)
	if options.filter_bad:
		bad_line_count_per_slice = [sum(data[1]) for data in analysis_res]
		lines = [num - b for num, b in zip(lines, bad_line_count_per_slice)]
		bad_line_count_total = sum(bad_line_count_per_slice)
		if bad_line_count_total:
			print('Slice   Bad line count')
			for sliceno, cnt in enumerate(bad_line_count_per_slice):
				print('%5d   %d' % (sliceno, cnt,))
			print('total   %d' % (bad_line_count_total,))
			print()
			print('Slice   Bad line number')
			reported_count = 0
			for sliceno, data in enumerate(analysis_res):
				if sum(data[1]) and reported_count < 32:
					with open('badmap%d' % (sliceno,), 'rb') as fh:
						badmap = mmap(fh.fileno(), 0, prot=PROT_READ)
						for ix, v in enumerate(imap(ord, badmap)):
							if v:
								for jx in range(8):
									if v & (1 << jx):
										print('%5d   %d' % (sliceno, ix * 8 + jx,))
										reported_count += 1
										if reported_count >= 32: break
								if reported_count >= 32: break
						badmap.close()
			if reported_count >= 32:
				print('...')
			print()
			print('Bad line count   Column')
			for colname in sorted(analysis_res[0][0]):
				cnt = sum(sum(data[0][colname]) for data in analysis_res)
				if cnt:
					print('%14d   %s' % (cnt, colname,))
			print()
		for sliceno in range(slices):
			unlink('badmap%d' % (sliceno,))
	if options.defaults and sum(sum(data[2].values()) for data in analysis_res):
		print('Defaulted values')
		for colname in sorted(options.defaults):
			defaulted = [data[2][colname] for data in analysis_res]
			if sum(defaulted):
				print('    %s:' % (colname,))
				print('        Slice   Defaulted line count')
				slicecnt = 0
				for sliceno, cnt in enumerate(defaulted):
					if cnt:
						print('        %5d   %d' % (sliceno, cnt,))
						slicecnt += 1
				if slicecnt > 1:
					print('        total   %d' % (sum(defaulted),))
	if dws: # rehashing
		if dw: # not as a chain
			for colname in dw.columns:
				for sliceno in range(slices):
					out_fn = dw.column_filename(colname, sliceno=sliceno)
					with open(out_fn, 'wb') as out_fh:
						for s in range(slices):
							src_fn = dws[s].column_filename(colname, sliceno=sliceno)
							with open(src_fn, 'rb') as in_fh:
								copyfileobj(in_fh, out_fh)
			for sliced_dw in dws:
				sliced_dw.discard()
			for sliceno, counts in enumerate(zip(*[data[4] for data in analysis_res])):
				bad_counts = (data[1][sliceno] for data in analysis_res)
				dw.set_lines(sliceno, sum(counts) - sum(bad_counts))
			for sliceno, data in enumerate(analysis_res):
				dw.set_minmax(sliceno, data[3])
		else:
			for sliceno, data in enumerate(analysis_res):
				dws[sliceno].set_minmax(-1, data[3])
				for s, count in enumerate(data[4]):
					dws[sliceno].set_lines(s, count - data[1][s])
	else:
		for sliceno, count in enumerate(lines):
			dw.set_lines(sliceno, count)
		for sliceno, data in enumerate(analysis_res):
			dw.set_minmax(sliceno, data[3])
