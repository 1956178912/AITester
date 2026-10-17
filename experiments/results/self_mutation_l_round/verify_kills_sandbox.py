"""Sandbox-verify: apply each L-round mutant to a temp copy and run the new test file."""
import sys, tempfile, pathlib
sys.path.insert(0, '.')
from experiments.mutation_testing import ExtendedMutationGenerator
from scripts.tools.self_mutation import Sandbox, _mutant_id, classify_result

MIDS = ['helpers:5f59874830d1','helpers:5f886043809a','helpers:a3ee749e3485','helpers:cc058e223acc',
        'helpers:608205e3bd2f','helpers:f95a3a18c5c3','helpers:a93688ca6eb0','helpers:29836f6132a3',
        'helpers:925bf0576cf6','helpers:396a28db8ca8','helpers:e6b7f907a2b1',
        'helpers:383bf2851ceb']
REL = 'src/utils/helpers.py'
TEST = 'tests/test_self_mutation_survivors_l.py'
src = pathlib.Path(REL).read_text(encoding='utf-8')
gen = ExtendedMutationGenerator(max_per_task=10_000)
by_id = {_mutant_id('helpers', m): m for m in gen.generate(src)}
base = pathlib.Path(tempfile.mkdtemp(prefix='l_verify_'))
sandbox = Sandbox.create(base / 'w0', pathlib.Path('.').resolve(), module_paths=[REL], test_files=[TEST], label='verify')
cmd = '{python} -m pytest {test_files} -q --tb=no -x -p no:cacheprovider -o addopts='
try:
    proc = sandbox.run_tests([TEST], cmd, timeout=180)
    print('baseline rc=', proc.returncode, '->', 'GREEN' if proc.returncode == 0 else 'RED')
    for mid in MIDS:
        sandbox.apply_mutant(REL, by_id[mid].code)
        try:
            p = sandbox.run_tests([TEST], cmd, timeout=180)
        finally:
            sandbox.restore_module(REL)
        outcome, reason = classify_result(p.returncode, getattr(p, 'timed_out', False))
        print(f'{mid}: rc={p.returncode} -> {outcome} {"<-- EXPECTED KILLED" if outcome=="killed" else "<-- !! NOT KILLED"}')
finally:
    sandbox.close()
