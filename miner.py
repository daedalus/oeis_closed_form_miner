# Copyright Darío Clavijo 2023.

import re
import os
import sys
import json
import requests
import sqlite3
import lzo
from functools import cache
from sage.all import CFiniteSequences, QQ, sage_eval, var

ALGORITHMS = ['sage', 'pari']
OEIS_DATA_DIR = 'oeis_data'
OEIS_DB_PATH = os.path.join(OEIS_DATA_DIR, 'oeis.db')
SEQUENCE_MODE = "lzo"

OEIS_FORMULA_REGEX_1 = '^a\(n\)\s\=\s(.*)\.\s\-\s\_(.*)\_\,(.*)$'
OEIS_FORMULA_REGEX_2 = '^a\(n\)\s\=\s(.*)\.$'
OEIS_FORMULA_REGEX_3 = '^a\(n\)\s\=\s(.*)\.|(\s\-\s\_(.*)\_\,(.*))$'


def regex_match(regex, expression):
    """
    Matches an expression (formula in the OEIS format) to a regex.

    Args:
        regex (str): Regular expression pattern.
        expression (str): Expression to match.

    Returns:
        str or None: A string representation of a formula.
    """
    try:
        match_groups = re.match(regex, expression).groups()
        if match_groups and len(match_groups) > 0:
            return match_groups[0]
    except Exception:
        return None


@cache
def string_to_expression(s):
    """
    Evaluate a string to a SageMath expression.

    Args:
        s (str): Input string.

    Returns:
        Expression: A SageMath expression.
    """
    return sage_eval(s, locals={'n': var('x')})


def simplify_expression(cf):
    """
    Simplify expression to a string.

    Args:
        cf: Expression.

    Returns:
        str or None: Simplified expression.
    """
    try:
        return str(cf.full_simplify().operands()[0])
    except Exception:
        return None


def formula_match(formulas, closed_form):
    """
    Extracts every formula from a list in the OEIS format, then matches every formula to a closed_form.

    Args:
        formulas (list): List of formulas.
        closed_form (str): Closed form string.

    Returns:
        bool: True if there is a match.
    """
    if len(closed_form) == 0:
        return False

    try:
        fexp1 = string_to_expression(closed_form)
    except Exception:
        return False

    for formula in formulas:
        if (r_formula := regex_match(OEIS_FORMULA_REGEX_3, formula)) is not None:
            try:
                fexp2 = string_to_expression(r_formula)
                if bool(fexp1 == fexp2):
                    return True
            except Exception:
                pass

    return False


def get_sequence(sequence_id):
    """
    Fetches the OEIS sequence information for the given ID from the OEIS website.

    Args:
        sequence_id (str): The OEIS sequence ID.

    Returns:
        dict or None: The sequence information in dictionary format or None if fetching fails.
    """
    try:
        response = requests.get(f"https://oeis.org/search?fmt=json&q=id:{sequence_id}")
        return json.loads(response.content)
    except Exception as e:
        return None


def load_cached_sequence(sequence_id):
    """
    Loads a previously cached OEIS sequence data from the local storage.

    Args:
        sequence_id (str): The OEIS sequence ID.

    Returns:
        dict or None: The cached sequence data in dictionary format or None if not found.
    """
    n = sequence_id[1:4]
    file_path = None

    file_path0 = os.path.join(OEIS_DATA_DIR, f'{sequence_id}.{SEQUENCE_MODE}')
    if os.path.isfile(file_path0):
        file_path = file_path0

    file_path1 = os.path.join(OEIS_DATA_DIR, n, f'{sequence_id}.{SEQUENCE_MODE}')
    if os.path.isfile(file_path1):
        file_path = file_path1

    if file_path is not None:
        with open(file_path, 'rb') as fp:
            if SEQUENCE_MODE == 'lzo':
                return json.loads(lzo.decompress(fp.read()))
            else:
                return json.loads(fp.read())

    return None


def save_cached_sequence(sequence_id, data):
    """
    Saves the OEIS sequence data to the local cache.

    Args:
        sequence_id (str): The OEIS sequence ID.
        data (dict): The sequence data to be cached.
    """
    n = sequence_id[1:4]
    directory_path = f"{OEIS_DATA_DIR}/{n}"
    if not os.path.isdir(directory_path):
        os.makedirs(directory_path)

    file_path = os.path.join(directory_path, f'{sequence_id}.{SEQUENCE_MODE}')
    with open(file_path, 'wb') as fp:
        raw_data = json.dumps(data)
        if SEQUENCE_MODE == 'lzo':
            comp_data = lzo.compress(raw_data,9)
            fp.write(comp_data)
            return len(raw_data),len(comp_data)
        else:
            fp.write(raw_data.encode("utf8"))
            return len(raw_data),0

def guess_sequence(lst):
    """
    Guesses the closed form of an integer sequence.

    Args:
        lst (list): List of integers representing the sequence.

    Returns:
        object or None: The guessed closed form or None if no closed form is found.
    """
    C = CFiniteSequences(QQ)
    for algo in ALGORITHMS:
        if (s := C.guess(lst, algorithm=algo)) != 0:
            return s.closed_form(), algo


def check_sequence(data, items=10):
    """
    Checks a small portion of terms of the sequence first and then the whole sequence.

    Args:
        data (list): List of integers representing the sequence.
        items (int): Number of items to check initially.

    Returns:
        object or None: The guessed closed form or None if no closed form is found.
    """
    first_terms_data = data[:items]
    if len(first_terms_data) > 7 and (result := guess_sequence(first_terms_data)) is not None:
        return guess_sequence(data)


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
                    "simplified_closed_form TEXT, new INT, regex_match INT, keyword TEXT, algo TEXT)")
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


def download_only_remaining(start,end):
    conn = sqlite3.connect(OEIS_DB_PATH)
    cursor = conn.cursor()
    #for n, sequence_id in enumerate(yield_unprocessed_ids(cursor)):
    for n in range(start,end):
        sequence_id = "A%06d" % n
        raw_data = get_sequence(sequence_id)
        bz,cz = save_cached_sequence(sequence_id, raw_data)
        print("sequence id:", sequence_id, bz, "uncompressed bytes", cz, "compressed_bytes")

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
    hard_count = 0
    not_easy_count = 0
    BLACKLIST = ['A004921', 'A131921']

    for n, sequence_id in enumerate(yield_unprocessed_ids(cursor)):
        if sequence_id in BLACKLIST:
            continue

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
            keyword = raw_data['results'][0]['keyword']
            l_formula, formula = [], ''
            if 'formula' in raw_data['results'][0]:
                l_formula = raw_data['results'][0]['formula']
                formula = json.dumps(l_formula)
            if regex_match(OEIS_FORMULA_REGEX_2, name) is not None:
                l_formula.append(name)

            closed_form = ""
            simplified_closed_form = ""
            algo = None
            is_new = False
            v_regex_match = False
           
            if (cf_algo := check_sequence([int(x) for x in data.split(",")])) is not None:
                cf, algo = cf_algo
                found_count += 1
                closed_form = str(cf)

                if len(closed_form) > 1 and not (cf.is_integer() and cf.is_constant()):
                    simplified_closed_form = simplify_expression(cf)

                    is_new = (closed_form is not None and closed_form not in name and closed_form not in formula)
                    is_new |= (simplified_closed_form is not None and simplified_closed_form not in name and
                               simplified_closed_form not in formula)
                    is_new &= not (v_regex_match := formula_match(l_formula, closed_form))

                    #sql = """UPDATE sequence SET name=?, data=?, formula=?, closed_form=?, simplified_closed_form=?, new=?, regex_match=?, keyword=?, algo=? WHERE id=?"""
                    #cursor.execute(sql, (name, data, formula, closed_form, simplified_closed_form, int(is_new),
                    #                     int(v_regex_match), keyword, algo, sequence_id))

                    if is_new:
                        new_count += 1
                        if keyword.find("hard") > -1:
                            hard_count += 1
                        if keyword.find("easy") == -1:
                            not_easy_count += 1
                        print(80 * "=")
                        print("ID:", sequence_id)
                        print("NAME:", name)
                        print(80 * "-")
                        print("CLOSED_FORM:", closed_form, "len:", len(closed_form))
                        if simplified_closed_form is not None and len(simplified_closed_form) > 0:
                            print("SIMP_CLOSED_FORM:", simplified_closed_form, "len:",
                                  len(simplified_closed_form))
                        else:
                            print(sequence_id, "maxima could not simplify", closed_form)
                        print("keywords:", keyword)
                        print("algo:", algo)
                        print(80 * "-")
                        if found_count > 0 and new_count > 0:
                            print("PROC: %d, FOUND: %d, NEW: %d, RATIO (P/F): %.3f, RATIO (F/N): %.3f, RATIO(P/N): %.3f, HARD: %d, NOT EASY: %d"
                                  % (proc, found_count, new_count, proc / found_count, found_count / new_count,
                                     proc / new_count, hard_count, not_easy_count))
                        print(string_to_expression.cache_info())
            
            sql = """UPDATE sequence SET name=?, data=?, formula=?, closed_form=?, simplified_closed_form=?, new=?, regex_match=?, keyword=?, algo=? WHERE id=?"""
            cursor.execute(sql, (name, data, formula, closed_form, simplified_closed_form, int(is_new),
                int(v_regex_match), keyword, algo, sequence_id))
 
        else:
            fail_count += 1
            if fail_count == 10:
                print("Failed last: %d sequences..." % fail_count)
                sys.exit(-1)

        if n % 10 == 0:
            conn.commit()


if __name__ == "__main__":
    create_database(368_000)
    if len(sys.argv) > 1 and sys.argv[1] == "-d":
        download_only_remaining(int(sys.argv[2]),int(sys.argv[3]))
    else:
        process_sequences()
