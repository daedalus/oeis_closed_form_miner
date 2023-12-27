# Copyright Darío Clavijo 2023.

import re
import os
import sys
import json
import requests
import sqlite3
import lzo
from sage.all import CFiniteSequences, QQ, sage_eval, var

OEIS_DATA_DIR = 'oeis_data'
OEIS_DB_PATH = os.path.join(OEIS_DATA_DIR, 'oeis.db')
SEQUENCE_MODE = "lzo"


def regex_match(exp):
  """
  Matches an expresion (formula in the OEIS format) to a regex:
  Args: 
      exp: expresion.
  Returns:
      A string representation of a formula.
  """
  r = '^a\(n\)\s\=\s(.*)\.\s\-\s\_(.*)\_\,(.*)$'
  try:
    if len(b:=re.match(r,exp).groups()) > 0: return b[0]
  except: return None


def formula_match(formulas, closed_form):
  """
  It extracts every formula from a list in the OEIS format then
  matches every formula in the list to a closed_form.
  Args:
      list of formulas, closed_form string.
  Returns: 
      True if match.
  """
  if len(closed_form) == 0: return False
  x = var('x')
  try:
    fexp1 = sage_eval(closed_form,locals={'n':x})
  except:
    return False
  for formula in formulas:
    if (rformula := regex_match(formula)) is not None:
      try:
        fexp2 = sage_eval(rformula,locals={'n':x})
        if bool(fexp1 == fexp2): return True
      except: pass
  return False

def get_sequence(id):
    """
    Fetches the OEIS sequence information for the given ID from the OEIS website.

    Args:
        id (str): The OEIS sequence ID.

    Returns:
        dict or None: The sequence information in dictionary format or None if fetching fails.
    """
    try:
        response = requests.get(f"https://oeis.org/search?fmt=json&q=id:{id}")
        return json.loads(response.content)
    except Exception as e:
        return None


def load_cached_sequence(id):
    """
    Loads a previously cached OEIS sequence data from the local storage.

    Args:
        id (str): The OEIS sequence ID.

    Returns:
        dict or None: The cached sequence data in dictionary format or None if not found.
    """
    file_path = os.path.join(OEIS_DATA_DIR, f'{id}.{SEQUENCE_MODE}')
    if os.path.isfile(file_path):
        with open(file_path, 'rb') as fp:
            if SEQUENCE_MODE == 'lzo':
                return json.loads(lzo.decompress(fp.read()))
            else:
                return json.loads(fp.read())
    return None


def save_cached_sequence(id, data):
    """
    Saves the OEIS sequence data to the local cache.

    Args:
        id (str): The OEIS sequence ID.
        data (dict): The sequence data to be cached.
    """
    file_path = os.path.join(OEIS_DATA_DIR, f'{id}.{SEQUENCE_MODE}')
    with open(file_path, 'wb') as fp:
        if SEQUENCE_MODE == 'lzo':
            fp.write(lzo.compress(json.dumps(data), 9))
        else:
            fp.write(json.dumps(data).encode("utf8"))


def guess_sequence(lst):
    """
    Guesses the closed form of an integer sequence.

    Args:
        lst (list): List of integers representing the sequence.

    Returns:
        object or None: The guessed closed form or None if no closed form is found.
    """
    return None if (s := CFiniteSequences(QQ).guess(lst)) == 0 else s.closed_form()

def check_sequence(data, items=10):
    """
    Checks a small portion of terms of the sequence first and then the whole sequence.

    Args:
        data (list): List of integers representing the sequence.
        items (int): Number of items to check initially.

    Returns:
        object or None: The guessed closed form or None if no closed form is found.
    """
    seq = data[:items]
    if len(seq) > 7 and (result := guess_sequence(seq)) is not None:
        seq = data
        return guess_sequence(seq)


def process_file():
    """
    Processes the sequence IDs from a file and prints their corresponding sequence information.
    """
    ids = [line.rstrip() for line in open(sys.argv[1], 'r').readlines()]
    for sequence_id in ids:
        print(sequence_id, get_sequence(sequence_id))


def create_database(length):
    """
    Creates a blank database with a table for storing OEIS sequence information.

    Args:
        length (int): The number of sequences to prepopulate the database with.
    """
    if not os.path.isfile(OEIS_DB_PATH):
        conn = sqlite3.connect(OEIS_DB_PATH)
        cur = conn.cursor()
        cur.execute("CREATE TABLE sequence(id, name TEXT, data TEXT, formula TEXT, closed_form TEXT, "
                    "simplified_closed_form TEXT, new INT, regex_match INT)")
        for n in range(1, length + 1):
            cur.execute("INSERT INTO sequence (id) VALUES ('A%06d');" % n)
        conn.commit()


def yield_unprocessed_ids(cursor):
    """
    Yields a generator of unvisited sequences from the database.

    Args:
        cursor (sqlite3.Cursor): SQLite database cursor.

    Yields:
        str: The next unvisited sequence ID.
    """
    cursor.execute("SELECT id FROM sequence WHERE name IS NULL;")
    for row in cursor.fetchall():
        yield row[0]


def process_sequences():
    """
    Processes sequences from the generator:
    - Fetches each unvisited sequence from the server or local cache.
    - Guesses its closed form and matches it to name and formula.
    - Saves everything to the database and prints statistics.
    """
    conn = sqlite3.connect(OEIS_DB_PATH)
    cursor = conn.cursor()
    fail_count = 0
    new_count = 0
    found_count = 0
    for n, sequence_id in enumerate(yield_unprocessed_ids(cursor)):
        cached_data = load_cached_sequence(sequence_id)
        if cached_data is not None:
            raw_data = cached_data
        else:
            raw_data = get_sequence(sequence_id)
            save_cached_sequence(sequence_id, raw_data)

        if raw_data is not None:
            fail_count = 0
            proc = n + 1
            name = raw_data['results'][0]['name']
            data = raw_data['results'][0]['data']
            lformula,formula = [],''
            if 'formula' in raw_data['results'][0]:
              lformula = raw_data['results'][0]['formula']
              formula = json.dumps(lformula)
            closed_form = ""
            simplified_closed_form = ""
            if (cf := check_sequence([int(x) for x in data.split(",")])) is not None:
                found_count += 1
                closed_form = str(cf)
                try:
                    simplified_closed_form = str(cf.full_simplify().operands()[0])
                except Exception:
                    simplified_closed_form = ""
            is_new = (closed_form is not None and closed_form not in name and closed_form not in formula)  
            is_new |= (simplified_closed_form is not None and simplified_closed_form not in name and simplified_closed_form not in formula)
            regex_match = formula_match(lformula, closed_form) 
            is_new &= not regex_match

            sql = """UPDATE sequence SET name=?, data=?, formula=?, closed_form=?, simplified_closed_form=?, new=?, regex_match=? WHERE id=?"""
            cursor.execute(sql, (name, data, formula, closed_form, simplified_closed_form, int(is_new), int(regex_match), sequence_id))
            if is_new:
            #if regex_match:
                new_count += 1
                print(80 * "=")
                print("ID:", sequence_id)
                print("NAME:", name)
                print(80 * "-")
                print("CLOSED_FORM:", closed_form, "len:", len(closed_form))
                if simplified_closed_form is not None:
                    print("SIMP_CLOSED_FORM:", simplified_closed_form, "len:", len(simplified_closed_form))
                else:
                    print(sequence_id, "maxima could not simplify", closed_form)
                print("regex_match:", regex_match)
                print(80 * "-")
                if found_count > 0 and new_count > 0:
                  print("PROC: %d, FOUND: %d, NEW: %d, RATIO (P/F): %.3f, RATIO (F/N): %.3f"
                      % (proc, found_count, new_count, proc / found_count, found_count / new_count))
        else:
            fail_count += 1
            if fail_count == 10:
                print("Failed last: %d sequences..." % fail_count)
                sys.exit(-1)
        if n % 10 == 0:
            conn.commit()


if __name__ == "__main__":
    create_database(368_000)
    process_sequences()
