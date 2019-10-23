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

from __future__ import print_function
from __future__ import division

from optparse import OptionParser
import sys
from importlib import import_module
from os.path import realpath
from os import environ

from accelerator.compat import quote_plus, PY3, getarglist

from accelerator import automata_common
from accelerator.dispatch import JobError


def find_automata(a, package, script):
	if package:
		package = [package]
	else:
		package = sorted(a.config()['method_directories'])
	if not script:
		script = 'automata'
	if not script.startswith('automata'):
		script = 'automata_' + script
	for p in package:
		module_name = p + '.' + script
		try:
			module_ref = import_module(module_name)
			print(module_name)
			return module_ref
		except ImportError as e:
			if PY3:
				if not e.msg[:-1].endswith(script):
					raise
			else:
				if not e.message.endswith(script):
					raise
	raise Exception('No automata "%s" found in {%s}' % (script, ', '.join(package)))

def run_automata(options):
	if options.port:
		assert not options.socket, "Specify either socket or port (with optional hostname)"
		url = 'http://' + (options.hostname or 'localhost') + ':' + str(options.port)
	else:
		assert not options.hostname, "Specify either socket or port (with optional hostname)"
		url = 'unixhttp://' + quote_plus(realpath(options.socket or './socket.dir/default'))

	a = automata_common.Automata(url, verbose=options.verbose, flags=options.flags.split(','), infoprints=True, print_full_jobpath=options.print_full_jobpath)

	if options.abort:
		a.abort()
		return

	try:
		a.wait(ignore_old_errors=not options.just_wait)
	except JobError:
		# An error occured in a job we didn't start, which is not our problem.
		pass

	if options.just_wait:
		return

	module_ref = find_automata(a, options.package, options.script)

	assert getarglist(module_ref.main) == ['urd'], "Only urd-enabled automatas are supported"
	if 'URD_AUTH' in environ:
		user, password = environ['URD_AUTH'].split(':', 1)
	else:
		user, password = None, None
	info = a.info()
	urd = automata_common.Urd(a, info, user, password, options.horizon)
	if options.quick:
		a.update_method_deps()
	else:
		a.update_methods()
	module_ref.main(urd)


def main(argv):
	parser = OptionParser(usage="Usage: %prog [options] [script]")
	parser.add_option('-p', '--port',     dest="port",     default=None,        help="framework listening port", )
	parser.add_option('-H', '--hostname', dest="hostname", default=None,        help="framework hostname", )
	parser.add_option('-S', '--socket',   dest="socket",   default=None,        help="framework unix socket (default ./socket.dir/default)", )
	parser.add_option('-s', '--script',   dest="script",   default=None      ,  help="automata script to run. package/[automata_]script.py. default \"automata\". Can be bare arg too.",)
	parser.add_option('-P', '--package',  dest="package",  default=None      ,  help="package where to look for script, default all method directories in alphabetical order", )
	parser.add_option('-f', '--flags',    dest="flags",    default='',          help="comma separated list of flags", )
	parser.add_option('-A', '--abort',    dest="abort",    action='store_true', help="abort (fail) currently running job(s)", )
	parser.add_option('-q', '--quick',    dest="quick",    action='store_true', help="skip method updates and checking workdirs for new jobs", )
	parser.add_option('-w', '--just_wait',dest="just_wait",action='store_true', help="just wait for running job, don't run any automata", )
	parser.add_option('-F', '--fullpath', dest="print_full_jobpath", action='store_true', help="print full path to jobdirs")
	parser.add_option('--verbose',        dest="verbose",  default='status',    help="verbosity style {no, status, dots, log}")
	parser.add_option('--quiet',          dest="quiet",    action='store_true', help="same as --verbose=no")
	parser.add_option('--horizon',        dest="horizon",  default=None,        help="Time horizon - dates after this are not visible in urd.latest")

	options, args = parser.parse_args(argv)
	if len(args) == 1:
		assert options.script is None, "Don't specify both --script and a bare script name."
		options.script = args[0]
	else:
		assert not args, "Don't know what to do with args %r" % (args,)

	options.verbose = {'no': False, 'status': True, 'dots': 'dots', 'log': 'log'}[options.verbose]
	if options.quiet: options.verbose = False

	try:
		run_automata(options)
		return 0
	except JobError:
		# If it's a JobError we don't care about the local traceback,
		# we want to see the job traceback, and maybe know what line
		# we built the job on.
		print_minimal_traceback()
	return 1


def print_minimal_traceback():
	ac_fn = automata_common.__file__
	if ac_fn[-4:] in ('.pyc', '.pyo',):
		# stupid python2
		ac_fn = ac_fn[:-1]
	blacklist_fns = {ac_fn}
	last_interesting = None
	_, e, tb = sys.exc_info()
	while tb is not None:
		code = tb.tb_frame.f_code
		if code.co_filename not in blacklist_fns:
			last_interesting = tb
		tb = tb.tb_next
	lineno = last_interesting.tb_lineno
	filename = last_interesting.tb_frame.f_code.co_filename
	print("Failed to build job %s on %s line %d" % (e.jobid, filename, lineno,))
