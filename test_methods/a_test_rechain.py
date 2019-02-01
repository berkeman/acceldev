############################################################################
#                                                                          #
# Copyright (c) 2019 Carl Drougge                                          #
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
from __future__ import unicode_literals

description = r'''
Test re-using datasets (from test_selfchain) in new
chains, and verify that the old chain still works.
Also tests that the dataset cache is updated correctly
on re-chaining.
'''

from dataset import Dataset, DatasetWriter

jobids = ('selfchain',)

def synthesis(jobid):
	manual_chain = [Dataset(jobids.selfchain, name) for name in "abcdefgh"]
	manual_abf = [manual_chain[0], manual_chain[1], manual_chain[5]]
	# build a local abf chain
	prev = None
	for ix, ds in enumerate(manual_abf):
		name = "abf%d" % (ix,)
		ds.link_to_here(name, override_previous=prev)
		prev = (jobid, name,)
	manual_abf_data = list(Dataset.iterate_list(None, None, manual_abf))
	local_abf_data = list(Dataset(jobid, "abf2").iterate_chain(None, None))
	assert manual_abf_data == local_abf_data
	# disconnect h, verify there is no chain
	manual_chain[-1].link_to_here("alone", override_previous=None)
	assert len(Dataset(jobid, "alone").chain()) == 1
	# check that the original chain is unhurt
	assert manual_chain == manual_chain[-1].chain()

	# So far so good, now make a chain long enough to have a cache.
	prev = None
	ix = 0
	going = True
	while going:
		if prev and "cache" in Dataset(prev)._data:
			going = False
		name = "longchain%d" % (ix,)
		dw = DatasetWriter(name=name, previous=prev)
		dw.add("ix", "number")
		dw.get_split_write()(ix)
		dw.finish()
		prev = (jobid, name,)
		ix += 1
	# we now have a chain that goes one past the first cache point
	full_chain = Dataset(prev).chain()
	assert "cache" in full_chain[-2]._data # just to check the above logic is correct
	assert "cache" not in full_chain[-1]._data # just to be sure..
	full_chain[-2].link_to_here("nocache", override_previous=None)
	full_chain[-1].link_to_here("withcache", override_previous=full_chain[-3])
	assert "cache" not in Dataset(jobid, "nocache")._data
	assert "cache" in Dataset(jobid, "withcache")._data
