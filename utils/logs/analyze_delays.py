# SPDX-FileCopyrightText: 2023-present Inria
# SPDX-FileCopyrightText: 2023-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Python script used to analyze delays between LH2 packets received by the controller, sorted by DotBot."""

# pylint: disable=import-error,invalid-name,unspecified-encoding

import os
import sys
from datetime import datetime
from io import StringIO

import matplotlib.pyplot as plt
import numpy as np
from logfmt_pandas import read_logfmt

# Check the logs file path
log_filename = "pydotbot.log"
if len(sys.argv) > 1:
    log_path = os.path.join(sys.argv[1], log_filename)
else:
    log_path = os.path.join(os.path.dirname(__file__), "..", "..", log_filename)

if not os.path.exists(log_path):
    print(f"Logs file not found: '{log_path}'")
    sys.exit(1)

# Load the log file as Pandas dataframe
with open(log_path) as log:
    df = read_logfmt(StringIO(log.read()))
df = df[df["event"] == "lh2"].filter(items=["timestamp", "source"])
sources = df["source"].unique()

bins = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5]
data = {}
print("======= Weights ========\n")
for source in sources:
    # Process the data into the update rate
    # ms / 100 (this helps make sure the pdf area calculation of the Histogram sums up to 100%)
    data[source] = (
        df[df["source"] == source]["timestamp"]
        .apply(lambda x: datetime.strptime(x, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
        .diff()
        * 1000
        / 100
    )
    data[source].dropna(inplace=True)
    print(f"--- {source} ---")
    np_hist = np.histogram(data[source], bins, density=True)
    print(np_hist[0])
    print("------------------------\n")


# Plot the results
fig, ax = plt.subplots(nrows=1, ncols=1)
ax.hist(
    data.values(),
    bins=bins,
    density=True,
    histtype="bar",
    label=[f"{e} ({len(data[e])} samples)" for e in list(data.keys())],
)

# Add labels and grids
ax.grid()
ax.legend()
ax.set_xticks(
    list(range(11)),
    ["", "100", "200", "300", "400", "500", "600", "700", "800", "900", "1000"],
)
ax.set_yticks(
    [e / 10 for e in list(range(11))],
    ["", "10%", "20%", "30%", "40%", "50%", "60%", "70%", "80%", "90%", "100%"],
)

ax.set_xlabel("Time between packets [ms]")
ax.set_ylabel("Percentage of Packets [%]")
ax.set_title("Delay between LH2 packets")

plt.show()
