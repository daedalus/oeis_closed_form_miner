#
# Copyright Darío Clavijo 2023.
#

from sage.all import *
import sys
import json
import requests
import sqlite3
import lzo
import base64
import pickle
import os

def getSequence1(id):
  try:
    f = requests.get("https://oeis.org/search?fmt=json&q=id:%s" % id)
    return json.loads(f.content)
  except:
    return None


def getSequence2(id):
  mode = "lzo"
  name = 'oeis_data/%s.%s' % (id, mode)
  if os.path.isfile(name):
    with open(name,'rb') as fp:
      if mode == 'lzo':
        return json.loads(lzo.decompress(fp.read()))
      else:
        return json.loads(fp.read())
  else:
    rep = requests.get("https://oeis.org/search?fmt=json&q=id:%s" % id)
    if rep.status_code == 200:
      data = json.loads(rep.content)
      with open(name,'wb') as fp:
        if mode == 'lzo':
          fp.write(lzo.compress(json.dumps(data),9))
        else:
          fp.write(json.dumps(data).encode("utf8"))
        fp.close()
      return data
    
getSequence = getSequence2


def guessSequence(lst):
  C = CFiniteSequences(QQ)
  if (s:= C.guess(lst)) == 0:
    return
  else:
    return s.closed_form()


def checkSequence(data,items=10):
  seq = data[:items]
  #print(len(seq))
  if len(seq) > 7 and (r:=guessSequence(seq)) is not None:
    seq = data
    return guessSequence(seq)


def procfile():
  IDS=[line.rstrip() for line in open(sys.argv[1],'r').readlines()]
  for id in IDS:
    print(id, getSequence(id))


def create_database(L):
  name = 'oeis_data/oeis.db' 
  if not os.path.isfile(name):
    conn = sqlite3.connect(name)
    cur = conn.cursor()
    cur.execute("CREATE TABLE sequence(id, name TEXT, data TEXT, formula TEXT, closed_form TEXT, simplified_closed_form TEXT, new INT)")
    for n in range(1, L + 1):
      cur.execute("insert into sequence (id) values ('A%06d');" % n)
    conn.commit()

def yield_unprocessed_ids(cursor):
  cursor.execute("SELECT id FROM sequence where name IS NULL;")
  for row in cursor.fetchall():
    yield row[0]


tointlist = lambda lst: [int(x) for x in lst.split(",")]

def process_sequences():
  conn = sqlite3.connect('oeis_data/oeis.db')
  cursor = conn.cursor()
  FAIL = 0
  NEW = 0
  FOUND = 0
  #PROC=0
  for n, id in enumerate(yield_unprocessed_ids(cursor)):
    if (raw_data := getSequence(id)) is not None:
      FAIL=0
      PROC=n+1
      N = raw_data['results'][0]['name']
      D = raw_data['results'][0]['data']
      F = ''
      if 'formula' in raw_data['results'][0]:
        F = json.dumps(raw_data['results'][0]['formula'])
      Fb = sqlite3.Binary(pickle.dumps(F, pickle.HIGHEST_PROTOCOL))
      sCF=""
      sSCF="" 
      if (CF := checkSequence(tointlist(D))) is not None:
        FOUND+=1
        sCF = str(CF) 
        try:
          sSCF = str(CF.full_simplify().operands()[0])
        except:
          sSCF = ""
          print("maxima could not simplify", sCF)
       
      sql = """update sequence set name = ?, data=?, formula=?, closed_form=?, simplified_closed_form=?, new=? where id=?""" 
      cursor.execute(sql,(N,D,Fb,sCF,sSCF,int(NEW),id))
      if (sCF is not None and sCF not in N and sCF not in F) or (sSCF is not None and sSCF not in N and sSCF not in F):
        NEW+=1
        print(80*"=")
        print("ID:",id)
        print("NAME:",N)
        print(80*"-")
        print("CLOSED_FORM:",sCF,"len:", len(sCF))
        print("SIMP_CLOSED_FORM:", sSCF,"len:", len(sSCF))
        print(80*"-")
        print("PROC: %d, FOUND: %d, NEW: %d, RATIO (P/F): %.3f, RATIO (F/N): %.3f" % (PROC, FOUND, NEW, PROC/FOUND, FOUND/NEW)) 
    else:
      FAIL += 1
      if FAIL == 10: 
        print("Failed last: %d sequences..." % FAIL)
        sys.exit(-1)
    if n % 10 == 0:
      conn.commit()

create_database(368_000)
process_sequences()
