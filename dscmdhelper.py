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

# common functionality for ds* commands

from __future__ import division, print_function

from os.path import join, exists, realpath

from accelerator.jobid import WORKSPACES
from accelerator.dataset import Dataset
from accelerator.jobid import get_path, get_workspace_name

def name2ds(n):
	if exists(n):
		# it's a path - dig out parts, maybe update WORKSPACES
		n = realpath(n)
		if n.endswith("/dataset.pickle"):
			n = n.rsplit("/", 1)[0]
		if exists(join(n, "dataset.pickle")):
			# includes ds name
			base, jid, name = n.rsplit("/", 2)
			n = (jid, name)
		else:
			# bare jid (no ds name)
			base, jid = n.rsplit("/", 1)
			n = jid
		k = jid.rsplit("-", 1)[0]
		if WORKSPACES.get(k, base) != base:
			print("### Overriding workdir %s to %s" % (k, base,))
		WORKSPACES[k] = base
	ds = Dataset(n)
	with open(join(get_path(ds.jobid), get_workspace_name(ds.jobid) + "-slices.conf")) as fh:
		slices = int(fh.read())
	from accelerator import g
	if hasattr(g, 'SLICES'):
		assert g.SLICES == slices, "Dataset %s needs %d slices, by we are already using %d slices" % (ds, slices, g.SLICES)
	else:
		g.SLICES = slices
	return ds
