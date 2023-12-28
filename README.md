# OEIS Closed Form Miner

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

1. Ensure the required dependencies are installed, including SageMath: `pip install -r requirements.txt`.
2. Run the script using `python miner.py`.
3. The script will create a database, process sequences, and print relevant statistics.
4. Querying the database for interesting things:
    1. `echo "select id, closed_form from sequence where keyword like '%hard%' and new=1" | sqlite3 oeis_data/oeis.db`
    2. `echo "select id, closed_form from sequence where keyword not like '%easy%' and new=1" | sqlite3 oeis_data/oeis.db`

## Dependencies

- Python libraries: `sqlite3`
- External libraries: `lzo` (for compression), `sage.all` (for mathematical analysis)

## License

This script is provided under the GPLv3 License. See the [LICENSE](LICENSE) file for details.

## Author

- Darío Clavijo

## Acknowledgments

Special thanks to the contributors to the OEIS and the SageMath library.

