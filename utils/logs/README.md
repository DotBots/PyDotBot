Logs parsing utilities
======================

This directory contains basic Python scripts that can be used to parse the logs
produced by the controller.

setup
-----

Install dependencies defined in `requirements.txt`

```
pip install -r requirements.txt
```

analyze_delays.py
-----------------

This script can be used to parse the logs and extract the information about LH2
packets received by the controller. The script prints the distribution weights
of delays (for 100ms, 200ms, etc) and displays the corresponding histogram.
Results are sorted for each DotBot found in the logs.

**Usage**

By default, this script tries to parse the default `pydotbot.log` created at the
base directory of this project. An optional directory containing `pydotbot.log`
can be given as parameter.

```
$ python analyze_delays.py <directory containing pydotbot.log>
```
