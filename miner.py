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
from tqdm import tqdm
from functools import cache
from sage.all import CFiniteSequences, QQ, ZZ, sage_eval, var
from sage.all_cmdline import fast_callable
from lib.pickling import *
from lib.blacklist import *

# Constants
ALGORITHMS = ['sage', 'pari']
OEIS_DATA_DIR = 'oeis_data'
OEIS_DB_PATH = os.path.join(OEIS_DATA_DIR, 'oeis.db')
XREF_PKL_FILE = os.path.join(OEIS_DATA_DIR, 'xref.pkl')
SEQUENCE_MODE = "lzo"

# Regular expressions
OEIS_FORMULA_REGEX_1 = '^a\(n\)\s\=\s(.*)\.\s\-\s\_(.*)\_\,(.*)$'
OEIS_FORMULA_REGEX_2 = '^a\(n\)\s\=\s(.*)\.$'
OEIS_FORMULA_REGEX_3 = '^a\(n\)\s\=\s(.*)\.|(\s\-\s\_(.*)\_\,(.*))$'
OEIS_FORMULA_REGEX_4 = '^a\(n\)\s\=\s(.*)\.$|a\(n\)\s\=\s(.*)\.(\s\-\s\_(.*)\_\,(.*))$'
OEIS_XREF_REGEX = 'A[0-9]{6}'

# Functions
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


def string_to_expression(s):
    """
    Evaluate a string to a SageMath expression.

    Args:
        s (str): Input string.

    Returns:
        Expression: A SageMath expression or None.
    """
    try:
        return sage_eval(s, locals={'n': var('x'),'x':var('x')})
    except Exception:
        return


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
    return matched if matched else None


def formula_match_exp(formula_exps, closed_form_exp):
    """
    Matches every formula expression to a closed form expression.

    Args:
        formulas (list): List of formulas expressions.
        closed_form_exp: Closed form expression.

    Returns:
        bool: True if there is a match.
    """
    #for f_exp in formula_exps:
    #    try:
    #        if f_exp == closed_form_exp:
    #            return True
    #    except Exception:
    #        pass
    #return False
    return any(f_exp == closed_form_exp for f_exp in formula_exps)

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
    file_paths = [
        os.path.join(OEIS_DATA_DIR, f'{sequence_id}.{SEQUENCE_MODE}'),
        os.path.join(OEIS_DATA_DIR, sequence_id[1:4], f'{sequence_id}.{SEQUENCE_MODE}'),
        os.path.join(OEIS_DATA_DIR, 'sequences', sequence_id[1:4], f'{sequence_id}.{SEQUENCE_MODE}')
    ]
    for file_path in file_paths:
        if os.path.isfile(file_path):
            with open(file_path, 'rb') as fp:
                if SEQUENCE_MODE == 'lzo':
                    return json.loads(lzo.decompress(fp.read()))
                elif SEQUENCE_MODE == 'lzogzip':
                    return json.loads(lzo.decompress(gzip.decompress(fp.read())))
                else:
                    return json.loads(fp.read())
    return None


def remove_cached_sequence(sequence_id):
    """
    Remove a given cache object.
    """
    file_paths = [
        os.path.join(OEIS_DATA_DIR, f'{sequence_id}.{SEQUENCE_MODE}'),
        os.path.join(OEIS_DATA_DIR, sequence_id[1:4], f'{sequence_id}.{SEQUENCE_MODE}'),
        os.path.join(OEIS_DATA_DIR, 'sequences', sequence_id[1:4], f'{sequence_id}.{SEQUENCE_MODE}')
    ]
    for file_path in file_paths:
        if os.path.isfile(file_path):
            os.remove(file_path)
            return True
    return False
    

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
            comp_data = lzo.compress(raw_data, 9)
            fp.write(comp_data)
            return len(raw_data), len(comp_data)
        elif SEQUENCE_MODE == 'lzogzip':
            comp_data = gzip.compress(lzo.compress(raw_data, 9), 9)
            fp.write(comp_data)
            return len(raw_data), len(comp_data)
        else:
            fp.write(raw_data.encode("utf8"))
            return len(raw_data), 0



@cache
def guess_sequence(lst, use_bm=False):
    """
    Guesses the closed form of an integer sequence.

    Args:
        lst (list): List of integers representing the sequence.

    Returns:
        object or None: The guessed closed form or None if no closed form is found.
    """
    if use_bm: ALGORITHMS.append("bm")
    for field in [ZZ,QQ]:
        C = CFiniteSequences(field)
        for algo in ALGORITHMS:
            if (s := C.guess(list(lst), algorithm=algo)) != 0:
                try:
                    return s.closed_form(), algo, str(field)
                except Exception:
                    return 


def check_sequence(data, items=10, use_bm=False):
    """
    Checks a small portion of terms of the sequence first and then the whole sequence.

    Args:
        data (list): List of integers representing the sequence.
        items (int): Number of items to check initially.

    Returns:
        object or None: The guessed closed form or None if no closed form is found.
    """
    first_terms_data = data[:items]
    if len(first_terms_data) > 7 and (result := guess_sequence(tuple(first_terms_data),use_bm=use_bm)) is not None:
        return guess_sequence(tuple(data), use_bm = use_bm)


def list_compare(A,B):
    """
    Compare elementwise two lists.
    Args:
        Lists: A,B.
    Returns:
        Boolean
    Comment:
        Still faster than: return all(A[n] == B[n] for n in range(0, len(A)))
    """
    for n in range(0,len(A)):
        if A[n] != B[n]: 
            return False
    return True


def expression_verify_sequence(exp, ground_truth_data):
    """
    Evaluates an expression and generates a sequence to check against ground truth data.
    Args:
        Expression, ground_truth_data
    Returns:
        Boolean
    """
    lg = len(ground_truth_data)
    try:
        fexp = fast_callable(exp, vars={'x':var('x')})
    except:
        return False
    e_data = []
    for n in tqdm(range(0, lg+1)):
        fx = fexp(n)
        try:
            e_data.append(int(fx.round()))
        except:
            e_data.append(fx)
    return list_compare(e_data[:lg - 1],ground_truth_data) or list_compare(e_data[1:], ground_truth_data)

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
        sys.stderr.write(f'Using database {OEIS_DB_PATH}...\n')
        sys.stderr.flush()
        return

    sys.stderr.write("Creating database {OEIS_DB_PATH}...\n")
    sys.stderr.flush()

    conn = sqlite3.connect(OEIS_DB_PATH)
    cur = conn.cursor()
    cur.execute("CREATE TABLE sequence(id, name TEXT, data TEXT, formula TEXT, closed_form TEXT, "
                "simplified_closed_form TEXT, new INT, regex_match INT, parsed_formulas TEXT, keyword TEXT, xref TEXT, algo TEXT, field TEXT, check_cf INT, not_easy INT, hard INT);")
    cur.execute("CREATE TABLE matches(id_a TEXT, id_b TEXT, formula_a TEXT, formula_b, TEXT);")
    cur.execute("CREATE TABLE blacklist(sequence_id TEXT);")

    for n in tqdm(range(1, length + 1)):
        cur.execute("INSERT INTO sequence (id) VALUES ('A%06d');" % n)

    for sequence_id in tqdm(BLACKLIST):
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


def yield_unprocessed_ids(cursor, reprocess = False):
    """
    Yields a generator of unvisited sequences from the database.

    Args:
        cursor (sqlite3.Cursor): SQLite database cursor.

    Yields:
        str: The next unvisited sequence ID.
    """
    if reprocess:
        cursor.execute("SELECT id FROM sequence WHERE (closed_form IS NULL or closed_form = '') and name is not NULL;")
    else:
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
    for n in tqdm(range(start,end)):
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


def process_sequences(ignore_blacklist=False, quiet=False, reprocess=False):
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
    check_cf = True

    seq_BLACKLIST = [] if ignore_blacklist else sorted(set(BLACKLIST + list(yield_blacklist(cursor)))) 

    for n, sequence_id in enumerate(yield_unprocessed_ids(cursor, reprocess=reprocess)):
        if sequence_id in seq_BLACKLIST:
            continue
    
        is_hard = False
        is_not_easy = False

        t0 = time.time()
        if not quiet:
            sys.stderr.write("Processing: %s...           \r" % sequence_id)
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
            if (keyword := raw_data['results'][0]['keyword']) == 'allocated':
                if not quiet:
                    print(sequence_id, keyword, "...")
                remove_cached_sequence(sequence_id)
                continue

            is_hard = keyword.find("hard") > -1
            is_not_easy = keyword.find("easy") == -1

            data = [int(x) for x in sdata.split(",")]
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
            field = None
            is_new = False
            v_regex_match = False
            v_check_cf = None

            if l_formula:
                formula_exps = formula_match_regex(OEIS_FORMULA_REGEX_4, l_formula)
            else:
                formula_exps = []

            if (cf_algo_field := check_sequence(data, use_bm=reprocess)) is not None:
                cf, algo, field = cf_algo_field
                found_count += 1
                closed_form = str(cf)

                if len(closed_form) > 1 and not (cf.is_integer() and cf.is_constant()):
                    simplified_closed_form = simplify_expression(cf)

                    is_new = (closed_form is not None and closed_form not in name and closed_form not in formula)
                    is_new |= (simplified_closed_form is not None and closed_form not in simplified_closed_form and 
                        simplified_closed_form not in name and simplified_closed_form not in formula)            
                    closed_form_exp = string_to_expression(closed_form)

                    if closed_form_exp is not None and formula_exps is not None:
                        is_new &= not (v_regex_match := formula_match_exp(formula_exps, closed_form_exp))
                                    
                    if check_cf:
                        v_check_cf = int(expression_verify_sequence(string_to_expression(closed_form), data))

                    if simplified_closed_form != closed_form: simplified_closed_form = None 

                    td = time.time() - t0
                    tc += td
                    m = max(m,td)

                    #if is_new and is_hard:
                    if is_new:
                        if is_hard:
                            hard_count += 1
                        if is_not_easy:
                            not_easy_count += 1

                        new_count += 1
                        if not quiet:
                            print(80 * "=")
                            print("ID:", sequence_id)
                            print("NAME:", name)
                            print(80 * "-")
                            print("CLOSED_FORM:", closed_form, "len:", len(closed_form))
                            if simplified_closed_form is not None and len(simplified_closed_form) > 0:
                                if simplified_closed_form != closed_form:
                                     print("SIMP_CLOSED_FORM:", simplified_closed_form, "len:", len(simplified_closed_form))
                            else:
                                print(sequence_id, "Maxima could not simplify:", closed_form)
                            print("len(data):",len(data))
                            print("keywords:", keyword)
                            print("xref:",xref)
                            print("algo:", algo)
                            print("field:", field)
                            print(80 * "-")

                            if found_count > 0 and new_count > 0:
                                print("PROC: %d, FOUND: %d, NEW: %d, RATIO (P/F): %.3f, RATIO (F/N): %.3f, RATIO(P/N): %.3f, HARD: %d, NOT EASY: %d, td: %.3f, avg: %.3f, max: %.3f"
                                    % (proc, found_count, new_count, proc / found_count, found_count / new_count,
                                         proc / new_count, hard_count, not_easy_count, td, tc/proc, m))
                            #print(formula_match_regex.cache_info())
                            print(guess_sequence.cache_info())
                else: 
                  closed_form = None
                  simplified_closed_form = None

            formula_exps_str = None
            if formula_exps is not None:
                formula_exps_str = json.dumps([str(f) for f in formula_exps]) 

            if simplified_closed_form == closed_form: simplified_closed_form = None
            
            sql = """UPDATE sequence SET name=?, data=?, formula=?, closed_form=?, simplified_closed_form=?, new=?, regex_match=?, parsed_formulas=?, keyword=?, xref=?, algo=?, field=?, check_cf=?, hard=?, not_easy=?  WHERE id=?"""
            cursor.execute(sql, (name, sdata, formula, closed_form, simplified_closed_form, int(is_new),
                int(v_regex_match), formula_exps_str, keyword, xref, algo, field, v_check_cf, is_hard, is_not_easy, sequence_id))
     
        else:
            fail_count += 1
            if fail_count == 10:
                sys.stderr.write(f"Failed last: {fail_count} sequences...\n")
                sys.stderr.flush()
                sys.exit(-1)

        if n % 10 == 0:
            conn.commit()

    cursor.execute("PRAGMA optimize;")
    conn.commit()


def yield_unchecked_closed_form(cursor):
    """
    yields rows from table sequence.
    """
    cursor.execute("select id, data , closed_form, new from sequence where closed_form is not NULL and check_cf is NULL order by id;")
    yield from cursor


def verify_sequences(ignore_blacklist=False):
    conn = sqlite3.connect(OEIS_DB_PATH)
    cursor1 = conn.cursor()
    cursor2 = conn.cursor()

    commit_size = 1000
    fail_count = 0
    check_count = 0
    proc = 0 
    e_BLACKLIST = [] if ignore_blacklist else BLACKLIST3

    for x, row in enumerate(yield_unchecked_closed_form(cursor1)):
        sequence_id = row[0]
        if sequence_id in e_BLACKLIST: continue
        data=[int(x) for x in row[1].split(",")]
        closed_form = row[2]
        new = row[3]
        if len(closed_form) > 1:
            proc += 1 
            exp = string_to_expression(closed_form)
            ok = expression_verify_sequence(exp, data)
            cursor2.execute("update sequence set check_cf=? where id=?;", (int(ok),sequence_id))
            print(f"id: {sequence_id}, cf: {closed_form}, new: {new}, ok: {ok}         ")
            if ok:
                check_count += 1
            else:
                fail_count += 1
        if x > 0 and x & commit_size == 0:
            conn.commit()
        if check_count > 0 and fail_count > 0:
            sys.stderr.write("sequence id: %s, PROC: %d, check: %d, fail: %d, RATIO(P/C): %.3f RATIO(P/F): %.3f \r" %(sequence_id, proc, check_count, fail_count, proc / check_count, proc / fail_count) )
            sys.stderr.flush()
    
    cursor2.execute("PRAGMA optimize;")
    conn.commit()


def process_xrefs(ignore_blacklist=False):
    """
    Tries to find new xrefs comparing equivalences in parsed formula expressions.
    Experimental feature: might not work or be removed in the future.
    """
    conn = sqlite3.connect(OEIS_DB_PATH)
    cursor = conn.cursor()

    fail_count = 0
    new_count = 0
    found_count = 0
    hard_count = 0
    not_easy_count = 0
    formula_count = 0
    e_BLACKLIST = [] if ignore_blacklist else BLACKLIST2

    D={}
    try:
        A = decompress_pickle(XREF_PKL_FILE)
    except:
        A = {}

    sys.stderr.write("Loading formulas from database...\n")
    sys.stderr.flush()

    for x, row in tqdm(enumerate(cursor.execute("select id, parsed_formulas from sequence where parsed_formulas is not NULL order by id;"))):
        if row[1] is not None:
            parsed_formulas = json.loads(row[1])
            sequence_id = row[0]
            D[sequence_id] = []
            for formula in parsed_formulas:
                if len(formula) > 1:
                    #sys.stderr.write(f"{x+1}, {sequence_id}, {formula}, {len(formula)}\r")
                    #sys.stderr.flush()
                    fexp = string_to_expression(formula)           
                    if fexp not in D[sequence_id]:
                        D[sequence_id].append(fexp)
                        formula_count += 1
    sys.stderr.write("done\n")
    sys.stderr.flush()

    sk = sorted(D.keys())
    lsk = len(sk)
    print("Total sequences to process: %d, formulas: %d, total work to do (n(n-1)/2): %d" % (lsk, formula_count, lsk*(lsk-1) // 2))
    for i in tqdm(range(0,lsk)):
        count = 0
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
                                cursor.execute(sql,(id_a,id_b, str(fexp_a), str(fexp_b)))
                                count += 1
                    A[id_a].append(id_b)  
        if count > 0:    
            compress_pickle(XREF_PKL_FILE, A)
            conn.commit()
        print(id_a, "processed xrefs:", len(A[id_a]))

    cursor.execute("PRAGMA optimize;")
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Process sequences and perform various tasks.')

    parser.add_argument('-d', '--download', nargs=2, metavar=('start', 'end'), type=int,
                        help='Download only remaining sequences in the specified range.')
    parser.add_argument('-x', '--process-xrefs', action='store_true', help='Process cross-references (experimental).')
    parser.add_argument('-b', '--add-to-blacklist', metavar='sequence', help='Add a sequence to the blacklist.')
    parser.add_argument('-i', '--ignore-blacklist', action='store_true', help='Ignore the blacklist.')
    parser.add_argument('-v', '--verify_sequences', action='store_true', help='Verify sequences')
    parser.add_argument('-q', '--quiet', action='store_true', help='Quiet mode (only prints new found closed forms).')
    parser.add_argument('-r', '--reprocess', action='store_true', help='Reprocess already processed sequences.')


    args = parser.parse_args()

    create_database(368_000)

    if args.download:
        download_only_remaining(args.download[0], args.download[1])
    elif args.process_xrefs:
        process_xrefs()
    elif args.add_to_blacklist:
        add_to_blacklist(args.add_to_blacklist)
    elif args.verify_sequences:
        verify_sequences(args.ignore_blacklist)
    elif args.ignore_blacklist:
        sys.stderr.write('Begin processing sequences (ignoring blacklist)...\n')
        process_sequences(True, quiet=args.quiet, reprocess = args.reprocess)
        sys.stderr.write('End.\n')
    else:
        sys.stderr.write('Begin processing sequences...\n')
        process_sequences(quiet=args.quiet, reprocess = args.reprocess)
        sys.stderr.write('End.\n')
    sys.stderr.flush()


if __name__ == "__main__":
    main()
