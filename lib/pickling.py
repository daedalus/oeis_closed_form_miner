import bz2
import sys
import os
try:
  import cPickle as pickle
except:
  import pickle

# Pickle a file and then compress it into a file with extension
def compress_pickle(filename, data):
    sys.stderr.write(f"saving pickle {filename}...\n")
    os.system(f"cp {filename} {filename}.bkp")
    with bz2.BZ2File(filename, "w") as f:
        pickle.dump(data, f)


# Load any compressed pickle file
def decompress_pickle(filename):
    sys.stderr.write(f"loading pickle {filename}...\n")
    data = bz2.BZ2File(filename, "rb")
    data = pickle.load(data)
    return data
