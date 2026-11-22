# Contributing

Please open a focused issue with a minimal, sharable pair of CSVs and the expected support set before proposing an algorithm change. Never include confidential CFD cases, personal data or unlicensed experimental files. Changes to coverage semantics must include a regression test exhibiting both a failure mode and the corrected result.

Install: `python -m pip install -e .`; test: `python -m unittest discover -s tests -v`. The development baseline is standard-library Python 3.10+; avoid mandatory scientific dependencies for the core demo. For external NASA data use pinned URLs and verify SHA-256 before changing any result. PRs are welcome; no CLA is requested by this project. Please disclose any scientific limitations or conflicting evidence.
