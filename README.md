# OEIS Closed Form Miner

[![CodeQL](https://github.com/daedalus/oeis_closed_form_miner/actions/workflows/codeql.yml/badge.svg)](https://github.com/daedalus/oeis_closed_form_miner/actions/workflows/codeql.yml)

## Overview

This Python script is designed to interact with the On-Line Encyclopedia of Integer Sequences [OEIS](https://oeis.org) to retrieve, process, and store information about integer sequences. The script uses a combination of web scraping, local caching, and database storage to analyze OEIS sequences and guess their closed forms.

## Features

### Fetching Sequence Information

- The script can fetch information about a specific OEIS sequence from the OEIS website.
- It supports caching the fetched data locally to improve performance.

### Sequence Analysis

- The script can guess the closed form of an integer sequence using SageMath.
- It checks a small portion of terms of the sequence first and then the whole sequence for better accuracy.

### Database Integration

- The script utilizes an SQLite database to store OEIS sequence information.
- It creates a prepopulated database table to efficiently manage sequence data.

### Sequence Processing

- The main functionality of the script involves processing sequences from the database:
  - Fetching unvisited sequences from the server or local cache.
  - Guessing closed forms and matching them to names and formulas.
  - Updating the database with the analyzed information.

### Statistics and Reporting

- The script prints statistics during the processing, including the number of processed, found, and new sequences.
- It also reports the ratio of processed to found sequences and the ratio of found to new sequences.

## Usage

1. Ensure the required system packages are installed: `apt install sagemath pari-gp maxima-sage-share python3-lzo`. 
2. Ensure the required dependencies are installed, including SageMath: `pip install -r requirements.txt`.
3. Download the oeis data (up to A366999): `git submodule init` and `git submodule update --remote`.
4. Run the script using `python miner.py` for normal download and processing.
    1. Alternatively `python miner.py -d start end` will download only sequnces from start to end with out processing.
5. The script will create a database, process sequences, and print relevant statistics.
6. Querying the database for interesting things:
    1. `echo "select id, algo, closed_form from sequence where hard=1 and check_cf=1 and new=1" | sqlite3 oeis_data/oeis.db`
    2. `echo "select id, algo, closed_form from sequence where not_easy=1 and check_cf=1 and new=1" | sqlite3 oeis_data/oeis.db`
7. Find new xrefs functionality: `python miner.py -x` will try to match symbolicaly every parsed formula in every sequence in the database.
8. There are some sequences that guessing its closed form hangs the process, for those sequences there is a blacklist in place that can be called with: `python miner.py -b sequence` to avoid processing them.

## Dependencies

- External packages: `sagemath`, `maxima-sage-share`, `pari-gp`.
- Python libraries: `sqlite3`, `lzo`, `tqdm`.

## License

This script is provided under the GPLv3 License. See the [LICENSE](LICENSE) file for details.

## Author

- Darío Clavijo

## Acknowledgments

Special thanks to the contributors to the OEIS and the SageMath library.

