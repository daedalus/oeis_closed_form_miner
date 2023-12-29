import bz2
import pickle
import _pickle as cPickle
import sys
import os

# Pickle a file and then compress it into a file with extension 
def compress_pickle(filename, data):
 sys.stderr.write(f"saving pickle {filename}...\n")
 os.system(f"cp {filename} {filename}.bkp")
 with bz2.BZ2File(filename, 'w') as f: 
   cPickle.dump(data, f)

# Load any compressed pickle file
def decompress_pickle(filename):
 sys.stderr.write(f"loading pickle {filename}...\n")
 data = bz2.BZ2File(filename, 'rb')
 data = cPickle.load(data)
 return data
