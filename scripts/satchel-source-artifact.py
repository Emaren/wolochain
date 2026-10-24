#!/usr/bin/env python3
"""Retired metadata-only source receipt; never accept it as artifact authority.

Use build-settlement-artifact.sh --profile composed-satcheld and the shared
settlement-artifact.py verifier with an authenticated external manifest digest.
Historical SOURCE_AUTHORITY.json files retain their original limited meaning.
"""

import sys


def build_receipt(_root):
    raise ValueError(
        "RETIRED_METADATA_ONLY_RECEIPT: use the composed-satcheld named profile "
        "in build-settlement-artifact.sh and settlement-artifact.py"
    )


if __name__ == "__main__":
    try:
        build_receipt(None)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
