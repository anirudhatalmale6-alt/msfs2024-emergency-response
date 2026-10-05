"""
STEP 2 - can we spawn a vehicle and drive it to your aircraft?

This is the last real technical risk in the project. Everything after it is
logic I can write and test myself.

It does two things:

  PART A  Tries to spawn each of a list of objects, and reports which ones the
          sim actually accepted. I do not know what the ground vehicles are
          called in MSFS 2024, so rather than guess once and fail, it tries
          several and tells us which exist.

  PART B  Takes whichever one worked, puts it a few hundred metres from you,
          and drives it over to park beside your aircraft.

Nothing is permanent. Anything spawned disappears when you end the flight.

HOW TO RUN
  Double-click RUN_STEP2.bat. Be in a flight, parked, engines off is fine.
  It writes result2.txt next to itself. Send me that.

Written on Linux and NOT run by me - I have no simulator. Expect the
possibility of an error; send it to me and it is still a useful answer.
"""

import ctypes
import logging
import os
import sys
import time

LOGFILE = 'result2.txt'


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

try:
    from SimConnect import SimConnect, AircraftRequests
    from SimConnect.Enum import SIMCONNECT_DATATYPE
    from SimConnect.Constants import SIMCONNECT_UNUSED
except ImportError as e:
    print('\nSimConnect library missing or changed: %s' % e)
    print('RUN_STEP2.bat should have installed it. Send me result2.txt.\n')
    sys.exit(1)

from response_geometry import (destination, distance_m, bearing_deg,
                               Aircraft, park_spots, Vehicle)


# The sim reports a failed spawn through its logger, not as a return value, so
# a bad object name would otherwise look exactly like a good one. Capture the
# warnings and we can tell the difference.
class Collect(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


COLLECT = Collect()
logging.getLogger('SimConnect').addHandler(COLLECT)
logging.getLogger('SimConnect').setLevel(logging.WARNING)


# Candidate objects to try, cheapest guess first. The last entry is the
# aircraft YOUR sim reported in step 1, so at least one entry is known to
# exist on your machine - that way we always learn something, even if every
# ground vehicle name is wrong.
CANDIDATES = [
    'Veh_Fire_Truck',
    'VEH_Fire_Truck',
    'Fire_Truck',
    'Veh_Ambulance',
    'Veh_Follow_Me',
    'FollowMe_Car',
    'Veh_Marshaller',
    'Veh_Baggage_Truck',
    'Veh_Fuel_Truck',
    'Veh_Pushback_Blue',
    'Pushback_Blue',
    'A350-900 (Default Cabin)',
]


def user_state(aq):
    g = lambda n: aq.get(n)
    return (g('PLANE_LATITUDE'), g('PLANE_LONGITUDE'),
            g('PLANE_ALTITUDE'), g('PLANE_HEADING_DEGREES_TRUE'))


def make_move_definition(sm):
    """A data definition holding position + heading, for writing to an object."""
    did = sm.new_def_id()
    fields = [(b'PLANE LATITUDE', b'degrees'),
              (b'PLANE LONGITUDE', b'degrees'),
              (b'PLANE ALTITUDE', b'feet'),
              (b'PLANE HEADING DEGREES TRUE', b'degrees')]
    for name, unit in fields:
        hr = sm.dll.AddToDataDefinition(
            sm.hSimConnect, did.value, name, unit,
            SIMCONNECT_DATATYPE.SIMCONNECT_DATATYPE_FLOAT64, 0, SIMCONNECT_UNUSED)
        if not sm.IsHR(hr, 0):
            raise RuntimeError('AddToDataDefinition failed for %s' % name)
    return did


def move_object(sm, did, object_id, lat, lon, alt, hdg):
    vals = [float(lat), float(lon), float(alt), float(hdg)]
    arr = (ctypes.c_double * len(vals))(*vals)
    ptr = ctypes.cast(arr, ctypes.c_void_p)
    hr = sm.dll.SetDataOnSimObject(
        sm.hSimConnect, did.value, int(object_id), 0, 0,
        ctypes.sizeof(ctypes.c_double) * len(vals), ptr)
    return sm.IsHR(hr, 0)


def try_spawn(sm, name, lat, lon, hdg):
    """Spawn one object and return its id, or None.

    The library stashes the assigned id in a single environment variable, so
    only one spawn can be in flight at a time - clear it first, spawn, then
    wait for it to appear. Spawning several at once would have them overwrite
    each other and we would lose track of which id belonged to which vehicle.
    """
    os.environ.pop('SIMCONNECT_OBJECT_ID', None)
    before = len(COLLECT.msgs)
    rqst = sm.new_request_id()
    try:
        sm.createSimulatedObject(name, lat, lon, rqst, hdg=hdg, gnd=1, alt=0)
    except Exception as e:
        return None, 'call raised %s' % e

    for _ in range(30):                       # up to ~3 s for the id to arrive
        time.sleep(0.1)
        oid = os.environ.get('SIMCONNECT_OBJECT_ID')
        if oid:
            return int(oid), 'ok'
    new = COLLECT.msgs[before:]
    return None, ('sim reported: %s' % '; '.join(new)) if new else 'no id came back'


def main():
    print('=' * 64)
    print('MSFS 2024 - STEP 2: spawn a vehicle and drive it to the aircraft')
    print('=' * 64)

    try:
        sm = SimConnect()
    except Exception as e:
        print('\nCOULD NOT CONNECT: %s' % e)
        print('MSFS must be running and you must be IN A FLIGHT.')
        sys.exit(1)
    print('\nCONNECTED.')
    aq = AircraftRequests(sm, _time=200)

    lat, lon, alt, hdg = user_state(aq)
    if lat is None:
        print('Could not read your aircraft position. Send me result2.txt.')
        sys.exit(1)
    print('Your aircraft: %.6f, %.6f  alt %.0f ft  heading %.0f'
          % (lat, lon, alt, hdg))

    # ---------------------------------------------------------- PART A
    print('\n' + '-' * 64)
    print('PART A - which objects will the sim actually spawn?')
    print('-' * 64)
    # put test spawns 400 m behind you so they are not inside your aircraft
    slat, slon = destination(lat, lon, (hdg + 180) % 360, 400.0)

    worked = []
    for name in CANDIDATES:
        oid, why = try_spawn(sm, name, slat, slon, hdg)
        if oid:
            print('  SPAWNED   %-28s id=%s' % (name, oid))
            worked.append((name, oid))
        else:
            print('  no        %-28s %s' % (name, why))

    print('\n%d of %d spawned.' % (len(worked), len(CANDIDATES)))
    if not worked:
        print('\nNothing spawned. That is a real answer, not a failure on your')
        print('part - it means I need a different approach for the vehicles.')
        print('Send me result2.txt and I will work out the next move.')
        sm.exit()
        return

    # ---------------------------------------------------------- PART B
    name, oid = worked[0]
    print('\n' + '-' * 64)
    print('PART B - driving "%s" over to your aircraft' % name)
    print('-' * 64)

    try:
        did = make_move_definition(sm)
    except Exception as e:
        print('Could not build the move definition: %s' % e)
        sm.exit()
        return

    ac = Aircraft(lat, lon, hdg, wingspan_m=64.75, length_m=66.8)   # A350-900
    tgt_lat, tgt_lon, tgt_face = park_spots(ac, 'fire')[0]
    print('Target: %.6f, %.6f  (%.0f m from you)'
          % (tgt_lat, tgt_lon, distance_m(lat, lon, tgt_lat, tgt_lon)))

    veh = Vehicle(slat, slon, heading=bearing_deg(slat, slon, tgt_lat, tgt_lon))
    ok_writes = failed_writes = 0
    t0 = time.time()
    for i in range(1200):                     # 2 minutes at 10 Hz
        veh.step(0.1, tgt_lat, tgt_lon)
        if move_object(sm, did, oid, veh.lat, veh.lon, alt, veh.heading):
            ok_writes += 1
        else:
            failed_writes += 1
        if i % 20 == 0:
            print('  %5.1fs  %6.0f m to go   speed %4.1f m/s'
                  % (time.time() - t0,
                     distance_m(veh.lat, veh.lon, tgt_lat, tgt_lon), veh.speed))
        if veh.arrived:
            break
        time.sleep(0.1)

    print('\nposition writes: %d accepted, %d rejected' % (ok_writes, failed_writes))
    if veh.arrived:
        print('ARRIVED after %.0f seconds.' % (time.time() - t0))
    else:
        print('Did not arrive within the time limit.')

    print('\nLOOK OUT OF THE WINDOW NOW.')
    print('Is there a vehicle parked off your left side? Did you see it drive?')
    print('Take a photo if you can - that tells me more than any number here.')
    time.sleep(10)

    if COLLECT.msgs:
        print('\nMessages the sim reported during the run:')
        for m in COLLECT.msgs[-25:]:
            print('  %s' % m)

    print('\nDone. Send me result2.txt.')
    sm.exit()


if __name__ == '__main__':
    main()
