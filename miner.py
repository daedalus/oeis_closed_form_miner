# Copyright Darío Clavijo 2023.

import os
import sys
import json
import requests
import sqlite3
import lzo
from sage.all import CFiniteSequences, QQ

OEIS_DATA_DIR = 'oeis_data'
OEIS_DB_PATH = os.path.join(OEIS_DATA_DIR, 'oeis.db')
SEQUENCE_MODE = "lzo"


def get_sequence(id):
    try:
        response = requests.get(f"https://oeis.org/search?fmt=json&q=id:{id}")
        return json.loads(response.content)
    except Exception as e:
        return None


def load_cached_sequence(id):
    file_path = os.path.join(OEIS_DATA_DIR, f'{id}.{SEQUENCE_MODE}')
    if os.path.isfile(file_path):
        with open(file_path, 'rb') as fp:
            if SEQUENCE_MODE == 'lzo':
                return json.loads(lzo.decompress(fp.read()))
            else:
                return json.loads(fp.read())
    return None


def save_cached_sequence(id, data):
    file_path = os.path.join(OEIS_DATA_DIR, f'{id}.{SEQUENCE_MODE}')
    with open(file_path, 'wb') as fp:
        if SEQUENCE_MODE == 'lzo':
            fp.write(lzo.compress(json.dumps(data), 9))
        else:
            fp.write(json.dumps(data).encode("utf8"))


def guess_sequence(lst):
    C = CFiniteSequences(QQ)
    if (s := C.guess(lst)) == 0:
        return None
    return s.closed_form()


def check_sequence(data, items=10):
    seq = data[:items]
    if len(seq) > 7 and (result := guess_sequence(seq)) is not None:
        seq = data
        return guess_sequence(seq)


def process_file():
    ids = [line.rstrip() for line in open(sys.argv[1], 'r').readlines()]
    for sequence_id in ids:
        print(sequence_id, get_sequence(sequence_id))


def create_database(length):
    if not os.path.isfile(OEIS_DB_PATH):
        conn = sqlite3.connect(OEIS_DB_PATH)
        cur = conn.cursor()
        cur.execute("CREATE TABLE sequence(id, name TEXT, data TEXT, formula TEXT, closed_form TEXT, "
                    "simplified_closed_form TEXT, new INT)")
        for n in range(1, length + 1):
            cur.execute("INSERT INTO sequence (id) VALUES ('A%06d');" % n)
        conn.commit()


def yield_unprocessed_ids(cursor):
    cursor.execute("SELECT id FROM sequence WHERE name IS NULL;")
    for row in cursor.fetchall():
        yield row[0]


def process_sequences():
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
            formula = '' if 'formula' not in raw_data['results'][0] else json.dumps(raw_data['results'][0]['formula'])
            closed_form = ""
            simplified_closed_form = ""
            if (cf := check_sequence(tointlist(data))) is not None:
                found_count += 1
                closed_form = str(cf)
                try:
                    simplified_closed_form = str(cf.full_simplify().operands()[0])
                except Exception:
                    simplified_closed_form = ""
            sql = """UPDATE sequence SET name=?, data=?, formula=?, closed_form=?, simplified_closed_form=?, new=? WHERE id=?"""
            cursor.execute(sql, (name, data, formula, closed_form, simplified_closed_form, int(new_count), sequence_id))
            if (closed_form is not None and closed_form not in name and closed_form not in formula) \
                    or (simplified_closed_form is not None and simplified_closed_form not in name and
                        simplified_closed_form not in formula):
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
                print(80 * "-")
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
