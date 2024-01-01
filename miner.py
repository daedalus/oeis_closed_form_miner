# Copyright Darío Clavijo 2023.

import re
import os
import sys
import time
import json
import requests
import sqlite3
import lzo
import gzip
import argparse
from functools import cache
from sage.all import CFiniteSequences, QQ, sage_eval, var
from lib.pickling import *

ALGORITHMS = ['sage', 'pari']
OEIS_DATA_DIR = 'oeis_data'
OEIS_DB_PATH = os.path.join(OEIS_DATA_DIR, 'oeis.db')
XREF_PKL_FILE = os.path.join(OEIS_DATA_DIR, 'xref.pkl')
SEQUENCE_MODE = "lzo"
#SEQUENCE_MODE = "lzogzip"

OEIS_FORMULA_REGEX_1 = '^a\(n\)\s\=\s(.*)\.\s\-\s\_(.*)\_\,(.*)$'
OEIS_FORMULA_REGEX_2 = '^a\(n\)\s\=\s(.*)\.$'
OEIS_FORMULA_REGEX_3 = '^a\(n\)\s\=\s(.*)\.|(\s\-\s\_(.*)\_\,(.*))$'
OEIS_FORMULA_REGEX_4 = '^a\(n\)\s\=\s(.*)\.$|a\(n\)\s\=\s(.*)\.(\s\-\s\_(.*)\_\,(.*))$'
OEIS_XREF_REGEX = 'A[0-9]{6}'

BLACKLIST = ['A004921', 'A008437', 'A014910', 'A022898', 'A022901', 'A069026', 'A080300', 'A084681', 'A090446', 'A094659', 'A094675', 'A131921', 'A136558','A156390','A156404','A157779'] # hard sequences for the moment we want to ignore them.


#@cache
def regex_match_one(regex, expression):
    """
    Matches an expression (formula in the OEIS format) to a regex.

    Args:
        regex (str): Regular expression pattern.
        expression (str): Expression to match.

    Returns:
        str or None: A string representation of a formula.
    """
    try:
        if (match_groups := re.match(regex, expression).groups()):
            return match_groups[1] if match_groups[0] is None else match_groups[0]
    except Exception:
        return None


#@cache
def string_to_expression(s):
    """
    Evaluate a string to a SageMath expression.

    Args:
        s (str): Input string.

    Returns:
        Expression: A SageMath expression.
    """
    return sage_eval(s, locals={'n': var('x'),'x':var('x')})


def simplify_expression(cf):
    """
    Simplify expression to a string.

    Args:
        cf: Expression.

    Returns:
        str or None: Simplified expression.
    """
    try:
        return str(cf.full_simplify())
    except Exception:
        return

@cache
def formula_match_regex(RE, formulas):
    """
    Matches a formula to a regex then validates it as an expression.
    Args:
        List of formulas in str format.
    Returns:
        List of valid expressions.
    """
    matched = []
    for formula in formulas:
        if (r_formula := regex_match_one(RE, formula)) is not None:
            try:
                matched.append(string_to_expression(r_formula))
            except Exception:
                pass
    if matched:
        return matched


def formula_match_exp(formula_exps, closed_form_exp):
    """
    Matches every formula expression to a closed form expression.

    Args:
        formulas (list): List of formulas expressions.
        closed_form_exp: Closed form expression.

    Returns:
        bool: True if there is a match.
    """
    for f_exp in formula_exps:
        try:
            if f_exp == closed_form_exp:
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

    file_path2 = os.path.join(OEIS_DATA_DIR,'sequences', n, f'{sequence_id}.{SEQUENCE_MODE}')
    if os.path.isfile(file_path2):
        file_path = file_path2


    if file_path is not None:
        with open(file_path, 'rb') as fp:
            if SEQUENCE_MODE == 'lzo':
                return json.loads(lzo.decompress(fp.read()))
            elif SEQUENCE_MODE == 'lzogzip':
                return json.loads(lzo.decompress(gzip.decompress(fp.read())))
            else:
                return json.loads(fp.read())


def save_cached_sequence(sequence_id, data):
    """
    Saves the OEIS sequence data to the local cache.

    Args:
        sequence_id (str): The OEIS sequence ID.
        data (dict): The sequence data to be cached.
    """
    n = sequence_id[1:4]
    directory_path = f"{OEIS_DATA_DIR}/sequences/{n}"
    if not os.path.isdir(directory_path):
        os.makedirs(directory_path)

    file_path = os.path.join(directory_path, f'{sequence_id}.{SEQUENCE_MODE}')
    with open(file_path, 'wb') as fp:
        raw_data = json.dumps(data)
        if SEQUENCE_MODE == 'lzo':
            comp_data = lzo.compress(raw_data,9)
            fp.write(comp_data)
            return len(raw_data),len(comp_data)
        elif SEQUENCE_MODE == 'lzogzip':
            comp_data = gzip.compress(lzo.compress(raw_data,9),9)
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
            try:
                return s.closed_form(), algo
            except Exception:
                return 

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
    if os.path.isfile(OEIS_DB_PATH):
        print(f'Using database {OEIS_DB_PATH}...')
        return

    conn = sqlite3.connect(OEIS_DB_PATH)
    cur = conn.cursor()
    cur.execute("CREATE TABLE sequence(id, name TEXT, data TEXT, formula TEXT, closed_form TEXT, "
                "simplified_closed_form TEXT, new INT, regex_match INT, parsed_formulas TEXT, keyword TEXT, xref TEXT, algo TEXT);")
    cur.execute("CREATE TABLE matches(id_a TEXT, id_b TEXT, formula_a TEXT, formula_b, TEXT);")
    cur.execute("CREATE TABLE blacklist(sequence_id TEXT);")

    for n in range(1, length + 1):
        cur.execute("INSERT INTO sequence (id) VALUES ('A%06d');" % n)

    for sequence_id in BLACKLIST:
        cur.execute("INSERT INTO blacklist (sequence_id) VALUES(?);", (sequence_id,))

    conn.commit()


def add_to_blacklist(sequence_ids):
    """
    Ads multiple sequence ids to the blacklist table.
    Args:
       string of ids.
    """
    conn = sqlite3.connect(OEIS_DB_PATH)
    cursor = conn.cursor()
    for sequence_id in re.findall(OEIS_XREF_REGEX, sequence_ids):
        cursor.execute("INSERT INTO blacklist (sequence_id) VALUES (?);", (sequence_id,))
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


def yield_blacklist(cursor):
    """
    Yields from the database a list of sequence ids in the blacklist.
    Args:
        cursor
    Yields:
        str: sequence id.   
    """
    cursor.execute("select sequence_id from blacklist order by sequence_id;")
    for row in cursor.fetchall():
        yield row[0]


def download_only_remaining(start,end):
    """
    Downloads sequences from the API in the range start,end.
    Args:
        start
        end
    """
    conn = sqlite3.connect(OEIS_DB_PATH)
    cursor = conn.cursor()
    fails = 0
    for n in range(start,end):
        fails = 0
        sequence_id = "A%06d" % n
        raw_data = get_sequence(sequence_id)
        if raw_data is not None:
            bz,cz = save_cached_sequence(sequence_id, raw_data)
            print("sequence id:", sequence_id, bz, "uncompressed bytes", cz, "compressed_bytes")
        else:
            fails += 1
        if fails == 10:
            print("Too many failed...")
            sys.exit(-1)


def process_sequences(ignore_blacklist=False):
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
    tc = 0
    m = 0

    if ignore_blacklist:
        seq_BACKLIST = []
    else:
        seq_BLACKLIST = sorted(set(BLACKLIST + list(yield_blacklist(cursor))))
    
    for n, sequence_id in enumerate(yield_unprocessed_ids(cursor)):
        if sequence_id in seq_BLACKLIST:
            continue
        t0 = time.time()
        sys.stderr.write("processing %s...           \r" % sequence_id)
        sys.stderr.flush()
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
            sdata = raw_data['results'][0]['data']
            data = [int(x) for x in sdata.split(",")]
            keyword = raw_data['results'][0]['keyword']
            xref = None
            if 'xref' in raw_data['results'][0]:
                xref = str(re.findall(OEIS_XREF_REGEX, str(raw_data['results'][0]['xref'])))
            l_formula, formula = [], ''
            if 'formula' in raw_data['results'][0]:
                l_formula = raw_data['results'][0]['formula']
                formula = json.dumps(l_formula)
            if (rname := regex_match_one(OEIS_FORMULA_REGEX_2, name)) is not None:
                l_formula.append(rname)

            closed_form = ""
            simplified_closed_form = ""
            algo = None
            is_new = False
            v_regex_match = False

            formula_exps = formula_match_regex(OEIS_FORMULA_REGEX_4, tuple(l_formula))
               
            if (cf_algo := check_sequence(data)) is not None:
                cf, algo = cf_algo
                found_count += 1
                closed_form = str(cf)

                if len(closed_form) > 1 and not (cf.is_integer() and cf.is_constant()):
                    simplified_closed_form = simplify_expression(cf)

                    is_new = (closed_form is not None and closed_form not in name and closed_form not in formula)
                    is_new |= (simplified_closed_form is not None and simplified_closed_form not in name and
                                   simplified_closed_form not in formula)
                        
                    try:
                        closed_form_exp = string_to_expression(closed_form)
                    except:
                        closed_form_exp = None

                    if closed_form_exp is not None and formula_exps is not None:
                        is_new &= not (v_regex_match := formula_match_exp(formula_exps, closed_form_exp))
                    
                    td = time.time() - t0
                    tc += td
                    m = max(m,td)

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
                        print("len(data):",len(data))
                        print("keywords:", keyword)
                        print("xref:",xref)
                        print("algo:", algo)
                        print(80 * "-")

                        if found_count > 0 and new_count > 0:
                            print("PROC: %d, FOUND: %d, NEW: %d, RATIO (P/F): %.3f, RATIO (F/N): %.3f, RATIO(P/N): %.3f, HARD: %d, NOT EASY: %d, td: %.3f, avg: %.3f, max: %.3f"
                                    % (proc, found_count, new_count, proc / found_count, found_count / new_count,
                                         proc / new_count, hard_count, not_easy_count, td, tc/proc, m))
                        print(formula_match_regex.cache_info())

               
            formula_exps_str = None
            if formula_exps is not None:
                formula_exps_str = json.dumps([str(f) for f in formula_exps]) 


            sql = """UPDATE sequence SET name=?, data=?, formula=?, closed_form=?, simplified_closed_form=?, new=?, regex_match=?, parsed_formulas=?, keyword=?, xref=?, algo=? WHERE id=?"""
            cursor.execute(sql, (name, sdata, formula, closed_form, simplified_closed_form, int(is_new),
                int(v_regex_match), formula_exps_str, keyword, xref, algo, sequence_id))
     
        else:
            fail_count += 1
            if fail_count == 10:
                print("Failed last: %d sequences..." % fail_count)
                sys.exit(-1)

        if n % 10 == 0:
            conn.commit()


def process_xrefs():
    """
    Tries to find new xrefs comparing equivalences in parsed formula expressions.
    """
    conn = sqlite3.connect(OEIS_DB_PATH)
    cursor = conn.cursor()

    fail_count = 0
    new_count = 0
    found_count = 0
    hard_count = 0
    not_easy_count = 0

    D={}
    try:
        A = decompress_pickle(XREF_PKL_FILE)
    except:
        A = {}

    global BLACKLIST
    BLACKLIST += ['A003775']
    formula_count = 0
    for x, row in enumerate(cursor.execute("select id, parsed_formulas from sequence where parsed_formulas is not NULL order by id;")):
        if row[1] is not None:
            parsed_formulas = json.loads(row[1])

            sequence_id = row[0]

            D[sequence_id] = []

            for formula in parsed_formulas:
                if len(formula) > 1:
                    print(x+1, sequence_id, formula, len(formula))
                    fexp = string_to_expression(formula)           
                    if fexp not in D[sequence_id]:
                        D[sequence_id].append(fexp)
                        formula_count += 1

    sk = sorted(D.keys())
    lsk = len(sk)
    print("Total sequences to process: %d, formulas: %d, total work to do (n(n-1)/2): %d" % (lsk, formula_count, lsk*(lsk-1) // 2))
    for i in range(0,lsk):
        id_a = sk[i]
        l_fexp_a = D[id_a]
        if id_a not in A: A[id_a] = []
        if id_a not in BLACKLIST:
            for j in range(i + 1, lsk):
                id_b = sk[j]
                sys.stderr.write("%s, %d of %d           \r" % (id_b,j-i,lsk-i))
                sys.stderr.flush()
                if id_b not in A[id_a] and id_b not in BLACKLIST:
                    l_fexp_b = D[id_b]
                    for fexp_a in l_fexp_a:
                        for fexp_b in l_fexp_b:
                            if fexp_a == fexp_b:
                                print("="*80)
                                print("new xref:")
                                print("seq a:", id_a, fexp_a, "seq b:", id_b, fexp_b)
                                print("-"*80)
                                sql = "insert into matches values (?,?,?,?);"
                                cur.execute(sql,(id_a,id_b, str(fexp_a), str(fexp_b)))
                    A[id_a].append(id_b)      
        compress_pickle(XREF_PKL_FILE, A)
        print(id_a, "processed xrefs:", len(A[id_a]))


def main():
    parser = argparse.ArgumentParser(description='Process sequences and perform various tasks.')

    parser.add_argument('-d', '--download', nargs=2, metavar=('start', 'end'), type=int,
                        help='Download only remaining sequences in the specified range.')
    parser.add_argument('-x', '--process-xrefs', action='store_true', help='Process cross-references.')
    parser.add_argument('-b', '--add-to-blacklist', metavar='sequence', help='Add a sequence to the blacklist.')
    parser.add_argument('-i', '--ignore-blacklist', action='store_true', help='Ignore the blacklist.')
    
    args = parser.parse_args()

    create_database(368_000)

    if args.download:
        download_only_remaining(args.download[0], args.download[1])
    elif args.process_xrefs:
        process_xrefs()
    elif args.add_to_blacklist:
        add_to_blacklist(args.add_to_blacklist)
    elif args.ignore_blacklist:
        print('Begin processing sequences (ignoring blacklist)...')
        process_sequences(True)
        print('End.')
    else:
        print('Begin processing sequences...')
        process_sequences()
        print('End.')

if __name__ == "__main__":
    main()

