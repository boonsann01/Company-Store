"""Run every suite. No dependencies beyond what the kiosk already needs.

    python tests/run_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ['test_database.py', 'test_routes.py']


def main():
    failed = []
    for suite in SUITES:
        result = subprocess.run([sys.executable, os.path.join(HERE, suite)], cwd=HERE)
        if result.returncode != 0:
            failed.append(suite)

    print('\n' + '=' * 60)
    if failed:
        print(f'FAILED: {", ".join(failed)}')
        return 1
    print(f'All {len(SUITES)} suites passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
