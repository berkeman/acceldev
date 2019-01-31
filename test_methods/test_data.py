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

# Test data for use in dataset testing

from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

from datetime import date, time, datetime

from compat import first_value

data = {
	"float64": (1/3, 1e100, -9.0),
	"float32": (100.0, -0.0, 2.0),
	"int64": (9223372036854775807, -9223372036854775807, 100),
	"int32": (-2147483647, 2147483647, -1),
	"bits64": (0, 18446744073709551615, 0x55aa55aa55aa55aa),
	"bits32": (0, 4294967295, 0xaa55aa55),
	"bool": (True, False, True,),
	"datetime": (datetime(1816, 2, 29, 23, 59, 59, 999999), datetime(1816, 2, 29, 23, 59, 59, 999998), datetime(1970, 1, 1, 0, 0, 0, 1)),
	"date": (date(2016, 2, 29), date(2016, 2, 28), date(2017, 6, 27),),
	"time": (time(12, 0, 0, 999999), time(12, 0, 0, 999998), time(0, 1, 2, 3)),
	"bytes": (b"foo", b"bar", b"blutti",),
	"unicode": ("bl\xe5", "bl\xe4", "bla",),
	"ascii": ("foo", "bar", "blutti",),
	# big value - will change if it roundtrips through (any type of) float
	"number": (1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000, -1.0, 1/3),
	"json": (42, None, "bl\xe4"),
}

value_cnt = {len(v) for v in data.values()}
assert len(value_cnt) == 1, "All tuples in data must have the same length."
value_cnt = first_value(value_cnt)

not_none_capable = {"bits64", "bits32",}
