"""Tests for the parking and driving maths.

These run anywhere - no simulator, no SimConnect, no Windows. That is the point:
this is the one part of the project I can actually prove is correct before it
ever goes near the sim.
"""
import math
import sys

from response_geometry import (
    destination, distance_m, bearing_deg, rel_bearing,
    Aircraft, FORMATIONS, MIN_MARGIN_M, MIN_STANDOFF_FACTOR, CLOSE_IN,
    park_spots, validate_formations,
    clears_airframe, is_forward_of_wing, Vehicle, drive,
)

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print('  PASS  %s' % name)
    else:
        print('  FAIL  %s   %s' % (name, detail))
        FAILS.append(name)


# An A320-ish aircraft parked at Heathrow, pointing roughly east.
AC = Aircraft(lat=51.4700, lon=-0.4543, heading=90.0,
              wingspan_m=35.8, length_m=37.6)


print('\n-- geodesy ----------------------------------------------------')

# Round trip: go out on a bearing, measure back. Must agree to centimetres,
# or every parking position is quietly in the wrong place.
for brg in (0, 45, 90, 180, 270, 359):
    for d in (10, 100, 1000):
        la, lo = destination(AC.lat, AC.lon, brg, d)
        back = distance_m(AC.lat, AC.lon, la, lo)
        bb = bearing_deg(AC.lat, AC.lon, la, lo)
        check('out %3d deg %4dm -> distance' % (brg, d), abs(back - d) < 0.05,
              'got %.4f' % back)
        check('out %3d deg %4dm -> bearing' % (brg, d),
              abs(rel_bearing(brg, bb)) < 0.01, 'got %.5f' % bb)

check('rel_bearing wraps left', abs(rel_bearing(10, 350) - -20) < 1e-9)
check('rel_bearing wraps right', abs(rel_bearing(350, 10) - 20) < 1e-9)


print('\n-- formation table --------------------------------------------')

# This is checked separately from the parked positions on purpose. park_spots()
# clamps a too-small distance up to a safe one, which means a position test can
# never catch a bad table - the clamp rescues it and the vehicle silently ends
# up somewhere other than where the table says. So check the table itself.
try:
    validate_formations()
    check('formation table is sane', True)
except ValueError as e:
    check('formation table is sane', False, str(e).replace('\n', ' '))

for service, spots in FORMATIONS.items():
    if service in CLOSE_IN:
        continue
    for rel, factor in spots:
        check('%s at %+.0f deg stands off far enough' % (service, rel),
              factor >= MIN_STANDOFF_FACTOR,
              'factor %.2f < %.2f' % (factor, MIN_STANDOFF_FACTOR))


print('\n-- parking positions ------------------------------------------')

for service, spots in ((s, park_spots(AC, s)) for s in FORMATIONS):
    check('%s: right number of vehicles' % service,
          len(spots) == len(FORMATIONS[service]))

    for i, (la, lo, facing) in enumerate(spots):
        d = distance_m(AC.lat, AC.lon, la, lo)
        # every vehicle must point back at the aircraft
        want = bearing_deg(la, lo, AC.lat, AC.lon)
        check('%s[%d] faces the aircraft' % (service, i),
              abs(rel_bearing(facing, want)) < 0.5,
              'facing %.2f, aircraft is at %.2f' % (facing, want))

        if service in ('fire', 'police', 'standby'):
            check('%s[%d] clears the airframe' % (service, i),
                  clears_airframe(AC, la, lo),
                  'only %.1f m out, need %.1f'
                  % (d, AC.radius + MIN_MARGIN_M))

# The ambulance is the deliberate exception - it comes in close, but it must be
# at the FORWARD door, never under a wing.
amb = park_spots(AC, 'medical')[0]
check('ambulance is forward of the wing',
      is_forward_of_wing(AC, amb[0], amb[1]))
check('ambulance is on the left side',
      rel_bearing(AC.heading, bearing_deg(AC.lat, AC.lon, amb[0], amb[1])) < 0)
check('ambulance is close in, not parked miles away',
      distance_m(AC.lat, AC.lon, amb[0], amb[1]) < AC.radius)

# Vehicles must not be parked on top of each other.
for service in FORMATIONS:
    spots = park_spots(AC, service)
    for i in range(len(spots)):
        for j in range(i + 1, len(spots)):
            d = distance_m(spots[i][0], spots[i][1], spots[j][0], spots[j][1])
            check('%s: vehicles %d and %d are apart' % (service, i, j), d > 9.0,
                  'only %.1f m' % d)

# A bigger aircraft must push the fire crews further out, not keep them at a
# fixed distance that would put them inside an A380's wing.
BIG = Aircraft(AC.lat, AC.lon, 90.0, wingspan_m=79.8, length_m=72.7)
small_d = distance_m(AC.lat, AC.lon, *park_spots(AC, 'fire')[0][:2])
big_d = distance_m(BIG.lat, BIG.lon, *park_spots(BIG, 'fire')[0][:2])
check('bigger aircraft -> crews stand further off', big_d > small_d + 20,
      '%.1f vs %.1f' % (big_d, small_d))
check('A380 fire spots still clear the airframe',
      all(clears_airframe(BIG, la, lo) for la, lo, _ in park_spots(BIG, 'fire')))


print('\n-- driving ----------------------------------------------------')

# Park a truck 400 m away and drive it to the aircraft's fire position.
tgt = park_spots(AC, 'fire')[0]
start_lat, start_lon = destination(AC.lat, AC.lon, 200.0, 400.0)

v = Vehicle(start_lat, start_lon, heading=0.0)
straight = distance_m(start_lat, start_lon, tgt[0], tgt[1])
secs, path = drive(v, tgt[0], tgt[1])

check('truck arrives', v.arrived, 'gave up after %.0f s' % secs)
check('stops on the mark', distance_m(v.lat, v.lon, tgt[0], tgt[1]) <= 2.0,
      '%.2f m short/over' % distance_m(v.lat, v.lon, tgt[0], tgt[1]))
check('comes to a stop', abs(v.speed) < 1e-9, 'speed %.3f' % v.speed)
check('takes a sensible time', 40 < secs < 180, '%.1f s for %.0f m' % (secs, straight))
check('does not wander', path < straight * 1.6,
      'drove %.0f m to cover %.0f m' % (path, straight))

# Never exceeds its speed limit, and never jumps.
v2 = Vehicle(start_lat, start_lon, heading=0.0, max_speed_ms=11.0)
worst = 0.0
for _ in range(6000):
    if v2.arrived:
        break
    pl, po = v2.lat, v2.lon
    v2.step(0.1, tgt[0], tgt[1])
    worst = max(worst, distance_m(pl, po, v2.lat, v2.lon) / 0.1)
check('never exceeds max speed', worst <= 11.0 + 1e-6, '%.3f m/s' % worst)

# Turn rate is respected even when the target is directly behind it.
v3 = Vehicle(AC.lat, AC.lon, heading=0.0, turn_rate_deg_s=45.0)
behind = destination(AC.lat, AC.lon, 180.0, 300.0)
worst_turn = 0.0
for _ in range(3000):
    if v3.arrived:
        break
    h0 = v3.heading
    v3.step(0.1, behind[0], behind[1])
    worst_turn = max(worst_turn, abs(rel_bearing(h0, v3.heading)) / 0.1)
check('never turns faster than its limit', worst_turn <= 45.0 + 1e-6,
      '%.3f deg/s' % worst_turn)
check('u-turn still arrives', v3.arrived)

# Already-there case must not crash or creep.
v4 = Vehicle(tgt[0], tgt[1], heading=0.0)
v4.step(0.1, tgt[0], tgt[1])
check('already at target -> arrived, no movement', v4.arrived and v4.speed == 0.0)


print('\n' + '=' * 62)
if FAILS:
    print('%d FAILED: %s' % (len(FAILS), ', '.join(FAILS[:6])))
    sys.exit(1)
print('all tests passed')
