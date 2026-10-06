"""Tests for the decision logic - which service, from what the sim can see.

Runs with no simulator. This is the part that decides whether a fire engine or
an ambulance turns up, so it is worth proving rather than hoping.
"""
import sys
import importlib.util

# import classify() without running the app
src = open('emergency_response.py').read()
src = src.split('def main()')[0]
src = src.replace('from SimConnect import SimConnect, AircraftRequests', 'pass')
src = src.replace('from SimConnect.Enum import SIMCONNECT_DATATYPE', 'pass')
src = src.replace('from SimConnect.Constants import SIMCONNECT_UNUSED', 'pass')
ns = {}
try:
    exec(compile(src, 'er', 'exec'), ns)
except SystemExit:
    pass
classify = ns['classify']
decode_squawk = ns['decode_squawk']


class FakeSim(object):
    """Stands in for the sim. Anything not set reads as 0, like a healthy jet."""

    def __init__(self, **vals):
        self.vals = vals

    def get(self, name, default=None):
        return self.vals.get(name, default if default is not None else 0)


SQ = {'2000': 8192, '7700': 30464, '7500': 29952, '7600': 30208}

CASES = [
    ('parked, nothing wrong',
     dict(TRANSPONDER_CODE=SQ['2000']), None),
    ('squawk 7700, healthy aircraft -> MEDICAL',
     dict(TRANSPONDER_CODE=SQ['7700'], FUEL_TOTAL_CAPACITY=1000,
          FUEL_TOTAL_QUANTITY=500), 'medical'),
    ('squawk 7500 -> POLICE',
     dict(TRANSPONDER_CODE=SQ['7500']), 'police'),
    ('engine 1 on fire, no squawk -> FIRE without being asked',
     dict(TRANSPONDER_CODE=SQ['2000'], ENG_ON_FIRE_1=1), 'fire'),
    ('engine 2 on fire -> FIRE (not just engine 1)',
     dict(TRANSPONDER_CODE=SQ['2000'], ENG_ON_FIRE_2=1), 'fire'),
    ('engine 4 on fire -> FIRE (four-engined aircraft)',
     dict(TRANSPONDER_CODE=SQ['2000'], ENG_ON_FIRE_4=1), 'fire'),
    ('fire AND 7700 -> FIRE, not medical',
     dict(TRANSPONDER_CODE=SQ['7700'], ENG_ON_FIRE_1=1), 'fire'),
    ('hijack outranks fire',
     dict(TRANSPONDER_CODE=SQ['7500'], ENG_ON_FIRE_1=1), 'police'),
    ('7700 + fuel below 5% -> FIRE standing by',
     dict(TRANSPONDER_CODE=SQ['7700'], FUEL_TOTAL_CAPACITY=1000,
          FUEL_TOTAL_QUANTITY=40), 'fire'),
    ('7700 + fuel at 6% -> still MEDICAL',
     dict(TRANSPONDER_CODE=SQ['7700'], FUEL_TOTAL_CAPACITY=1000,
          FUEL_TOTAL_QUANTITY=60), 'medical'),
    ('7600 radio failure is NOT an emergency response',
     dict(TRANSPONDER_CODE=SQ['7600']), None),
    ('no fuel data at all must not divide by zero',
     dict(TRANSPONDER_CODE=SQ['7700']), 'medical'),
]

fails = []


def sim_for(d):
    v = {}
    for k, val in d.items():
        if k == 'TRANSPONDER_CODE':
            v['TRANSPONDER_CODE:1'] = val
        elif k.startswith('ENG_ON_FIRE_'):
            v['ENG_ON_FIRE:%s' % k.rsplit('_', 1)[1]] = val
        else:
            v[k] = val
    return FakeSim(**v)


print('\n-- squawk decoding ---------------------------------------------')
for name, raw in SQ.items():
    got = decode_squawk(raw)
    ok = got == name
    print('  %-5s raw %-6d -> %s' % ('PASS' if ok else 'FAIL', raw, got))
    if not ok:
        fails.append('decode %s' % name)
print('  %-5s None -> %s' % ('PASS' if decode_squawk(None) == '----' else 'FAIL',
                             decode_squawk(None)))

print('\n-- which service turns up --------------------------------------')
for label, vals, want in CASES:
    try:
        got, why = classify(sim_for(vals))
    except Exception as e:
        got, why = 'EXCEPTION: %s' % e, ''
    ok = got == want
    print('  %-5s %-48s -> %s' % ('PASS' if ok else 'FAIL', label, got))
    if not ok:
        print('        expected %r, reason given: %r' % (want, why))
        fails.append(label)

print('\n' + '=' * 64)
if fails:
    print('%d FAILED: %s' % (len(fails), '; '.join(fails)))
    sys.exit(1)
print('all decision tests passed')
