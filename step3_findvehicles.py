"""
STEP 3 - find out what the ground vehicles are ACTUALLY called.

Step 2 proved we can spawn an object and drive it. Eleven of my twelve guessed
names were wrong, which is a naming problem, not a mechanism problem.

So stop guessing. Every spawnable object on your machine is declared in a
sim.cfg or aircraft.cfg file inside your MSFS folders, under "title=". This
reads them straight off your disk and gives us the real list.

Then it tries spawning the most promising ones, so we end up knowing not just
what exists but what actually works.

Reads files only. Changes nothing. Writes result3.txt and found_objects.txt.
"""

import os
import re
import sys
import time

LOGFILE = 'result3.txt'


class Tee(object):
    def __init__(self, stream, path):
        self.stream = stream
        self.fh = open(path, 'w', encoding='utf-8', errors='replace')

    def write(self, s):
        self.stream.write(s)
        self.stream.flush()
        self.fh.write(s)
        self.fh.flush()

    def flush(self):
        self.stream.flush()
        self.fh.flush()


try:
    sys.stdout = Tee(sys.stdout, LOGFILE)
except Exception:
    pass


# Folders that hold no .cfg worth reading but do hold tens of thousands of
# files. Skipping them turns a ten minute scan into a few seconds.
#
# NOT 'misc': the ground vehicles live in SimObjects\Misc, so pruning it would
# hide exactly what we are looking for and report "you have no vehicles" when
# in fact they were all sat there. Caught by testing the scan on a fake tree.
SKIP = {'scenery', 'texture', 'sound', 'soundai', 'effects', 'model',
        'contentinfo', 'navigationdata', 'propdefs'}

# What we care about, roughly in order of usefulness.
INTEREST = [
    ('FIRE',      ('fire', 'arff', 'crash', 'rescue', 'tender')),
    ('MEDICAL',   ('ambul', 'medic', 'hospital', 'paramedic')),
    ('POLICE',    ('police', 'security', 'patrol')),
    ('GROUND',    ('pushback', 'tug', 'baggage', 'catering', 'fuel', 'stair',
                   'belt', 'marshall', 'follow', 'gpu', 'deice', 'de_ice')),
    ('VEHICLE',   ('veh_', 'truck', 'car', 'van', 'bus', 'vehicle')),
]

# Real cfg lines look like any of these:
#     title = "Veh_Something"
#     title = "Veh_Something" ; Variation name
#     title=Veh_Something
# The first version of this kept the closing quote AND the trailing comment, so
# two thirds of the names came out as 'Veh_Something" ; Variation name' and
# could never spawn. Quoted form is matched first, and only then the bare form
# with anything after a ';' thrown away.
TITLE_QUOTED = re.compile(r'^\s*title\s*=\s*"([^"]*)"', re.IGNORECASE)
TITLE_BARE = re.compile(r'^\s*title\s*=\s*([^;"]+)', re.IGNORECASE)


def parse_title(line):
    m = TITLE_QUOTED.match(line)
    if m:
        return m.group(1).strip()
    m = TITLE_BARE.match(line)
    if m:
        return m.group(1).strip()
    return None


def user_cfg_paths():
    local = os.environ.get('LOCALAPPDATA', '')
    roaming = os.environ.get('APPDATA', '')
    return [
        os.path.join(local, 'Packages',
                     'Microsoft.Limitless_8wekyb3d8bbwe', 'LocalCache', 'UserCfg.opt'),
        os.path.join(roaming, 'Microsoft Flight Simulator 2024', 'UserCfg.opt'),
        os.path.join(local, 'Packages',
                     'Microsoft.FlightSimulator_8wekyb3d8bbwe', 'LocalCache', 'UserCfg.opt'),
        os.path.join(roaming, 'Microsoft Flight Simulator', 'UserCfg.opt'),
    ]


def find_roots():
    """Work out where the sim keeps its packages."""
    roots = []
    for cfg in user_cfg_paths():
        if not os.path.isfile(cfg):
            continue
        print('  found %s' % cfg)
        try:
            for line in open(cfg, 'r', errors='replace'):
                if 'InstalledPackagesPath' in line:
                    p = line.split('InstalledPackagesPath', 1)[1].strip().strip('"')
                    if os.path.isdir(p):
                        roots.append(p)
                        print('    packages at: %s' % p)
        except Exception as e:
            print('    could not read it: %s' % e)
    # common fallbacks, in case UserCfg.opt was not where expected
    for guess in (r'C:\MSFS2024', r'D:\MSFS2024', r'C:\MSFS', r'D:\MSFS',
                  os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Packages',
                               'Microsoft.Limitless_8wekyb3d8bbwe', 'LocalCache',
                               'Packages')):
        if guess and os.path.isdir(guess) and guess not in roots:
            roots.append(guess)
            print('    also found: %s' % guess)
    return roots


def scan(roots):
    titles = {}
    files = 0
    t0 = time.time()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP]
            for fn in filenames:
                if fn.lower() not in ('sim.cfg', 'aircraft.cfg'):
                    continue
                files += 1
                full = os.path.join(dirpath, fn)
                try:
                    for line in open(full, 'r', errors='replace'):
                        t = parse_title(line)
                        if t and t not in titles:
                            titles[t] = full
                except Exception:
                    pass
    print('  read %d cfg files in %.0f s -> %d distinct titles'
          % (files, time.time() - t0, len(titles)))
    return titles


NOISE = ('fsltl', 'fs_traffic', '_stub')


def is_noise(t):
    low = t.lower()
    return any(n in low for n in NOISE)


def categorise(titles):
    out = {}
    used = set()
    for label, words in INTEREST:
        hits = []
        for t in sorted(titles):
            if t in used or is_noise(t):
                continue
            low = t.lower()
            if any(w in low for w in words):
                hits.append(t)
                used.add(t)
        out[label] = hits
    return out


def main():
    print('=' * 64)
    print('STEP 3 - finding the real object names on your machine')
    print('=' * 64)

    print('\nLooking for your MSFS install...')
    roots = find_roots()
    if not roots:
        print('\nCould not find your MSFS packages folder.')
        print('Send me result3.txt and tell me where MSFS is installed.')
        return

    print('\nScanning (this can take a minute)...')
    titles = scan(roots)
    if not titles:
        print('\nFound no object titles at all. Send me result3.txt.')
        return

    with open('found_objects.txt', 'w', encoding='utf-8', errors='replace') as f:
        for t in sorted(titles):
            f.write('%s\n' % t)
    print('  full list written to found_objects.txt')

    cats = categorise(titles)
    print('\n' + '-' * 64)
    print('WHAT LOOKS USEFUL')
    print('-' * 64)
    candidates = []
    for label, _ in INTEREST:
        hits = cats[label]
        print('\n%s  (%d)' % (label, len(hits)))
        for t in hits[:25]:
            print('    %s' % t)
        if len(hits) > 25:
            print('    ... and %d more' % (len(hits) - 25))
        candidates.extend(hits[:10])

    if not candidates:
        print('\nNothing obviously emergency-related. The full list is in')
        print('found_objects.txt - send me that and I will pick from it.')
        return

    # ---- try spawning the best of them -------------------------------
    print('\n' + '-' * 64)
    print('TRYING TO SPAWN THE BEST %d' % min(len(candidates), 32))
    print('-' * 64)
    try:
        from SimConnect import SimConnect, AircraftRequests
    except ImportError:
        print('SimConnect not available, skipping the spawn test.')
        print('Send me result3.txt and found_objects.txt anyway.')
        return
    try:
        sm = SimConnect()
    except Exception as e:
        print('Sim not running (%s) - skipping the spawn test.' % e)
        print('That is fine. Send me result3.txt and found_objects.txt.')
        return

    import logging

    class Collect(logging.Handler):
        def __init__(self):
            logging.Handler.__init__(self)
            self.msgs = []

        def emit(self, record):
            self.msgs.append(record.getMessage())

    col = Collect()
    logging.getLogger('SimConnect').addHandler(col)
    logging.getLogger('SimConnect').setLevel(logging.WARNING)

    aq = AircraftRequests(sm, _time=200)
    lat, lon = aq.get('PLANE_LATITUDE'), aq.get('PLANE_LONGITUDE')
    hdg = aq.get('PLANE_HEADING_DEGREES_TRUE') or 0
    if lat is None:
        print('Could not read your position; skipping spawn test.')
        return

    worked = []
    for name in candidates[:32]:
        os.environ.pop('SIMCONNECT_OBJECT_ID', None)
        before = len(col.msgs)
        try:
            sm.createSimulatedObject(name, lat + 0.004, lon, sm.new_request_id(),
                                     hdg=hdg, gnd=1, alt=0)
        except Exception as e:
            print('  no        %-44s call raised %s' % (name[:44], e))
            continue
        oid = None
        for _ in range(25):
            time.sleep(0.1)
            oid = os.environ.get('SIMCONNECT_OBJECT_ID')
            if oid:
                break
        if oid:
            print('  SPAWNED   %-44s id=%s' % (name[:44], oid))
            worked.append(name)
        else:
            why = '; '.join(col.msgs[before:]) or 'no id came back'
            print('  no        %-44s %s' % (name[:44], why))

    print('\n%d of %d spawned.' % (len(worked), min(len(candidates), 32)))
    if worked:
        print('\nTHESE WORK - this is what I needed:')
        for w in worked:
            print('    %s' % w)
    sm.exit()
    print('\nDone. Send me result3.txt AND found_objects.txt.')


if __name__ == '__main__':
    main()
