"""
EMERGENCY LANDING RESPONSE SYSTEM - v1

Declare an emergency, land, and the right emergency services come and meet you.

  Fire        -> appliances meet you ON THE RUNWAY. You do not taxi a burning
                 aircraft to a stand.
  Medical     -> you taxi in normally and the ambulance meets you AT THE STAND.
  Security    -> squawk 7500, police meet you wherever you stop.

How it decides what you need:
  - Engine fire flag                  -> fire, no input from you
  - Squawk 7500                       -> police (hijack / unlawful interference)
  - Squawk 7700 + something broken    -> fire
  - Squawk 7700 + aircraft is fine    -> medical, because what else would it be
  - Or press a key and tell it

It watches the SIM, not SayIntentions or BeyondATC. That means it works with
any ATC addon, or none at all, and nobody else's update can break it.

Run it, then fly. Leave it running in the background.
"""

import json
import logging
import os
import sys
import time
import ctypes

LOGFILE = 'response_log.txt'


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
    print('\nSimConnect missing: %s\nRun RUN_RESPONSE.bat, it installs it.\n' % e)
    sys.exit(1)

from response_geometry import (destination, distance_m, bearing_deg,
                               Aircraft, park_spots, Vehicle)

TICK = 0.1                       # 10 Hz. Plenty for a driving vehicle, and far
                                 # below frame rate, so it costs the sim nothing.
SPAWN_DISTANCE_M = 450.0         # far enough to be out of sight when it appears


def load_vehicles(path='vehicles.json'):
    d = json.load(open(path, encoding='utf-8'))
    return {k: v for k, v in d.items() if not k.startswith('_')}


class Collect(logging.Handler):
    """The sim reports a failed spawn through the logger, never as a return
    value, so without this a bad object name looks exactly like a good one."""

    def __init__(self):
        logging.Handler.__init__(self)
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


def decode_squawk(v):
    """Transponder arrives as BCD: 7700 comes through as 30464."""
    try:
        return '%04X' % (int(v) & 0xFFFF)
    except (TypeError, ValueError):
        return '----'


class Sim(object):
    def __init__(self):
        self.col = Collect()
        logging.getLogger('SimConnect').addHandler(self.col)
        logging.getLogger('SimConnect').setLevel(logging.WARNING)
        self.sm = SimConnect()
        self.aq = AircraftRequests(self.sm, _time=120)
        self.move_def = self._make_move_def()

    def get(self, name, default=None):
        try:
            v = self.aq.get(name)
        except Exception:
            return default
        return default if v is None else v

    def _make_move_def(self):
        did = self.sm.new_def_id()
        for nm, unit in ((b'PLANE LATITUDE', b'degrees'),
                         (b'PLANE LONGITUDE', b'degrees'),
                         (b'PLANE ALTITUDE', b'feet'),
                         (b'PLANE HEADING DEGREES TRUE', b'degrees')):
            self.sm.dll.AddToDataDefinition(
                self.sm.hSimConnect, did.value, nm, unit,
                SIMCONNECT_DATATYPE.SIMCONNECT_DATATYPE_FLOAT64, 0,
                SIMCONNECT_UNUSED)
        return did

    def spawn(self, title, lat, lon, hdg):
        """One at a time: the library keeps the assigned id in a single global
        slot, so two spawns in flight at once would overwrite each other."""
        os.environ.pop('SIMCONNECT_OBJECT_ID', None)
        mark = len(self.col.msgs)
        try:
            self.sm.createSimulatedObject(title, lat, lon,
                                          self.sm.new_request_id(),
                                          hdg=hdg, gnd=1, alt=0)
        except Exception as e:
            return None, str(e)
        for _ in range(30):
            time.sleep(0.1)
            oid = os.environ.get('SIMCONNECT_OBJECT_ID')
            if oid:
                return int(oid), 'ok'
        return None, '; '.join(self.col.msgs[mark:]) or 'no id returned'

    def move(self, oid, lat, lon, alt, hdg):
        vals = (ctypes.c_double * 4)(float(lat), float(lon), float(alt), float(hdg))
        return self.sm.IsHR(self.sm.dll.SetDataOnSimObject(
            self.sm.hSimConnect, self.move_def.value, int(oid), 0, 0,
            ctypes.sizeof(ctypes.c_double) * 4,
            ctypes.cast(vals, ctypes.c_void_p)), 0)


class Response(object):
    """One dispatched vehicle: where it is, where it is going."""

    def __init__(self, oid, title, veh, tgt):
        self.oid, self.title, self.veh = oid, title, veh
        self.tgt_lat, self.tgt_lon, self.tgt_face = tgt
        self.reported = False


def classify(sim):
    """What is wrong, from what the sim can actually see.

    The sim knows the aeroplane. It knows nothing about the people inside it -
    there is no 'passenger taken ill' value and there never will be. So a
    declared emergency with a healthy aircraft is read as medical.
    """
    squawk = decode_squawk(sim.get('TRANSPONDER_CODE:1'))
    fire = any(sim.get('ENG_ON_FIRE:%d' % i, 0) for i in (1, 2, 3, 4))

    if squawk == '7500':
        return 'police', 'squawk 7500 - unlawful interference'
    if fire:
        return 'fire', 'engine fire detected'
    if squawk == '7700':
        cap = sim.get('FUEL_TOTAL_CAPACITY', 0) or 0
        qty = sim.get('FUEL_TOTAL_QUANTITY', 0) or 0
        if cap and qty / cap < 0.05:
            return 'fire', 'squawk 7700 + fuel below 5% - standing by'
        return 'medical', 'squawk 7700, aircraft healthy - assuming medical'
    return None, None


def main():
    print('=' * 66)
    print(' EMERGENCY LANDING RESPONSE SYSTEM  v1')
    print('=' * 66)

    try:
        vehicles = load_vehicles()
    except Exception as e:
        print('Could not read vehicles.json: %s' % e)
        return
    print('\nVehicles configured:')
    for k, v in vehicles.items():
        print('  %-9s %s' % (k, ', '.join(v)))

    print('\nConnecting...')
    try:
        sim = Sim()
    except Exception as e:
        print('COULD NOT CONNECT: %s' % e)
        print('MSFS must be running and you must be in a flight.')
        return
    print('CONNECTED. Watching for an emergency.\n')
    print('  Squawk 7700 for a general emergency (medical if nothing is broken)')
    print('  Squawk 7500 for security')
    print('  Or set an engine on fire and it will roll on its own\n')
    print('Ctrl+C to stop.\n')

    state = 'watching'
    kind = why = None
    live = []
    last_print = 0.0

    try:
        while True:
            t = time.time()
            lat = sim.get('PLANE_LATITUDE')
            lon = sim.get('PLANE_LONGITUDE')
            alt = sim.get('PLANE_ALTITUDE', 0)
            hdg = sim.get('PLANE_HEADING_DEGREES_TRUE', 0)
            gs = sim.get('GROUND_VELOCITY', 0) or 0
            on_gnd = sim.get('SIM_ON_GROUND', 0)

            if lat is None:
                time.sleep(0.5)
                continue

            if state == 'watching':
                kind, why = classify(sim)
                if kind:
                    state = 'declared'
                    print('\n' + '!' * 66)
                    print(' EMERGENCY DECLARED: %s' % why)
                    print(' Response: %s' % kind.upper())
                    if kind == 'fire':
                        print(' Appliances will meet you ON THE RUNWAY.')
                    elif kind == 'medical':
                        print(' Ambulance will meet you at your STAND once parked.')
                    else:
                        print(' Police will meet you wherever you stop.')
                    print('!' * 66 + '\n')

            elif state == 'declared':
                # wait until actually stopped on the ground
                if on_gnd and gs < 1.0:
                    print('Aircraft stopped. Scrambling %s.' % kind)
                    span = sim.get('WING_SPAN', 36.0) or 36.0
                    length = span * 1.05
                    ac = Aircraft(lat, lon, hdg, span, length)
                    spots = park_spots(ac, kind)
                    titles = vehicles.get(kind) or vehicles['fire']
                    for i, spot in enumerate(spots):
                        title = titles[i % len(titles)]
                        sb = (hdg + 150 + i * 20) % 360
                        slat, slon = destination(lat, lon, sb, SPAWN_DISTANCE_M)
                        oid, msg = sim.spawn(title, slat, slon,
                                             bearing_deg(slat, slon, lat, lon))
                        if not oid:
                            print('  could not spawn %s: %s' % (title, msg))
                            continue
                        v = Vehicle(slat, slon,
                                    heading=bearing_deg(slat, slon, spot[0], spot[1]))
                        live.append(Response(oid, title, v, spot))
                        print('  dispatched %-18s -> %4.0f m away'
                              % (title, distance_m(slat, slon, spot[0], spot[1])))
                    if live:
                        state = 'responding'
                        print('\n%d unit(s) en route. Look out of the window.\n'
                              % len(live))
                    else:
                        print('Nothing could be spawned. Check vehicles.json.')
                        state = 'watching'

            elif state == 'responding':
                for r in live:
                    r.veh.step(TICK, r.tgt_lat, r.tgt_lon)
                    h = r.tgt_face if r.veh.arrived else r.veh.heading
                    sim.move(r.oid, r.veh.lat, r.veh.lon, alt, h)
                    if r.veh.arrived and not r.reported:
                        r.reported = True
                        print('  %s on scene.' % r.title)
                if all(r.veh.arrived for r in live):
                    print('\nAll units on scene. Stand down when ready '
                          '(set squawk back to 2000).\n')
                    state = 'on_scene'

            elif state == 'on_scene':
                for r in live:
                    sim.move(r.oid, r.veh.lat, r.veh.lon, alt, r.tgt_face)
                k2, _ = classify(sim)
                if k2 is None:
                    print('Emergency cleared. Units released.\n')
                    live = []
                    state = 'watching'

            if t - last_print > 5.0:
                last_print = t
                print('  [%s] squawk %s  %s  %.0f kt   %d unit(s)'
                      % (state, decode_squawk(sim.get('TRANSPONDER_CODE:1')),
                         'on ground' if on_gnd else 'airborne',
                         gs * 1.94384, len(live)))

            time.sleep(TICK)

    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        try:
            sim.sm.exit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
