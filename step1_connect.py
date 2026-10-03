"""
STEP 1 - does SimConnect work on your MSFS 2024 install?

This does nothing to your sim. It only reads. It is the smallest possible test
of the one thing the whole project depends on.

HOW TO RUN
  1. Install Python 3 from python.org. Tick "Add Python to PATH" during install.
  2. Open Command Prompt and run:   pip install SimConnect
  3. Start MSFS 2024 and get into a flight (any aircraft, sat on the ground is fine).
  4. Run:   python step1_connect.py
  5. Copy everything it prints and send it to me.

WHAT I NEED TO KNOW
  Whether it connects, and which of the values come back as real numbers rather
  than FAILED. Send me the output either way - a failure here is still a useful
  answer and it is better to find out now.

Written on Linux, so I have not been able to run this myself. If it falls over
with a Python error, send me that too, errors are the most useful thing of all.
"""

import sys
import time

# ---------------------------------------------------------------- imports
try:
    from SimConnect import SimConnect, AircraftRequests
except ImportError:
    print('\nThe SimConnect library is not installed.')
    print('Open Command Prompt and run:   pip install SimConnect\n')
    sys.exit(1)


# The values the real project will depend on. Each line is:
#   (label, simvar name)
# TRANSPONDER CODE is the important one - that is how we detect squawk 7700
# without having to talk to SayIntentions or BeyondATC at all.
WANTED = [
    ('Transponder code',   'TRANSPONDER_CODE:1'),
    ('Latitude',           'PLANE_LATITUDE'),
    ('Longitude',          'PLANE_LONGITUDE'),
    ('Altitude (ft)',      'PLANE_ALTITUDE'),
    ('Heading (true)',     'PLANE_HEADING_DEGREES_TRUE'),
    ('Ground speed',       'GROUND_VELOCITY'),
    ('On the ground',      'SIM_ON_GROUND'),
    ('Engine 1 on fire',   'ENG_ON_FIRE:1'),
    ('Engine 2 on fire',   'ENG_ON_FIRE:2'),
    ('Fuel total (gal)',   'FUEL_TOTAL_QUANTITY'),
    ('Aircraft title',     'TITLE'),
]


def read(aq, name):
    """Read one simvar. Returns (value, how_it_was_read) or (None, reason).

    Deliberately does not swallow a failure into a tidy-looking zero: a probe
    that prints a plausible number when it actually read nothing is worse than
    one that says FAILED, because it sends us off building on a lie.
    """
    try:
        v = aq.get(name)
    except Exception as e:
        return None, 'error: %s' % e
    if v is None:
        return None, 'returned nothing (simvar may not exist in MSFS 2024)'
    return v, 'ok'


def decode_squawk(v):
    """The sim reports the transponder as BCD, not as the number you see.

    Squawk 7700 comes back as 0x7700 = 30464. Each group of 4 bits is one
    digit. So a raw value of 30464 is the aircraft squawking 7700 - without
    this, the number looks like nonsense and you would think it was broken.
    """
    try:
        n = int(v)
    except (TypeError, ValueError):
        return '?'
    return '%04X' % (n & 0xFFFF)


def main():
    print('=' * 64)
    print('MSFS 2024 SimConnect check')
    print('=' * 64)

    print('\nConnecting to the sim...')
    try:
        sm = SimConnect()
    except Exception as e:
        print('\nCOULD NOT CONNECT: %s' % e)
        print('\nUsual causes:')
        print('  - MSFS is not running, or you are still on the main menu.')
        print('    You need to be actually in a flight.')
        print('  - 32/64-bit Python mismatch. Use 64-bit Python.')
        print('\nSend me this whole message and I will sort it.')
        sys.exit(1)

    print('CONNECTED.\n')
    aq = AircraftRequests(sm, _time=200)

    ok = bad = 0
    print('%-20s %s' % ('VALUE', 'RESULT'))
    print('-' * 64)
    for label, name in WANTED:
        v, how = read(aq, name)
        if how == 'ok':
            ok += 1
            print('%-20s %s' % (label, v))
        else:
            bad += 1
            print('%-20s FAILED - %s' % (label, how))

    print('-' * 64)
    print('%d of %d values read successfully.\n' % (ok, ok + bad))

    # A live reading loop. Change the transponder to 7700 while this runs and
    # watch the number change - that is the whole detection mechanism, proven.
    print('Now reading live for 20 seconds.')
    print('While this runs, SET YOUR TRANSPONDER TO 7700 and watch it change.')
    print('(Ctrl+C to stop early.)\n')
    try:
        for i in range(20):
            sq, _ = read(aq, 'TRANSPONDER_CODE:1')
            gs, _ = read(aq, 'GROUND_VELOCITY')
            og, _ = read(aq, 'SIM_ON_GROUND')
            print('  squawk=%-6s (raw %-8s)  groundspeed=%-8s on_ground=%s'
                  % (decode_squawk(sq), sq,
                     round(gs, 1) if isinstance(gs, float) else gs, og))
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nStopped.')

    print('\nDone. Copy everything above and send it to me.')
    sm.exit()


if __name__ == '__main__':
    main()
