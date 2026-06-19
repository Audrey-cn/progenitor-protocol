import tempfile
import json
import os
import sys
import hashlib
from pathlib import Path

TEST_DATA_DIR = Path(__file__).parent / "_test_data"


def pytest_configure(config):
    TEST_DATA_DIR.mkdir(exist_ok=True)


def create_valid_gene(name, level="L1", gene_number="G99", creator="TestCreator",
                      description="A test gene for unit testing"):
    content = f'''# life_id: PGN@{level}-{gene_number}-{name.upper().replace("-", "_")}
# creator: {creator}
# description: {description}

def main():
    return {{"status": "success", "gene": "{name}"}}
'''
    return content


def create_malicious_gene():
    content = '''# life_id: PGN@L1-G99-MALICIOUS
# creator: Attacker
# description: Malicious gene with dangerous code

import os
import subprocess

def main():
    os.system("rm -rf /")
    eval("print('dangerous')")
    exec("import os; os.system('ls')")
    return {"status": "dangerous"}
'''
    return content


def create_invalid_lineage_gene():
    content = '''# life_id: EVIL@L1-G99-BAD-GENE
# creator: Attacker
# description: This gene has wrong lineage prefix

def main():
    return {"status": "void"}
'''
    return content


def create_third_party_import_gene():
    content = '''# life_id: PGN@L1-G99-NUMPY-GENE
# creator: TestCreator
# description: Gene that imports numpy

import numpy as np
import pandas as pd

def main():
    return {"status": "has_deps"}
'''
    return content


def save_temp_gene(content, name=None):
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if name is None:
        sha = hashlib.sha256(content.encode()).hexdigest()
        name = sha
    filepath = TEST_DATA_DIR / name
    filepath.write_text(content, encoding="utf-8")
    return filepath


def clean_test_data():
    if TEST_DATA_DIR.exists():
        for f in TEST_DATA_DIR.iterdir():
            f.unlink()
        TEST_DATA_DIR.rmdir()
