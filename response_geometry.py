"""Where the vehicles park, and how they drive there.

Deliberately knows nothing about SimConnect. Positions go in, positions come
out. That means it can be tested properly on a machine with no simulator on it,
which is the only part of this project I can verify myself - so it is worth
getting right here rather than discovering it is wrong in the sim.
"""
import math

R_EARTH = 6371008.8


# ---------------------------------------------------------------- geodesy
def destination(lat, lon, bearing_deg, dist_m):
    """Point `dist_m` away from (lat, lon) on a true bearing."""
    br = math.radians(bearing_deg)
    d = dist_m / R_EARTH
    la, lo = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la) * math.cos(d) +
                    math.cos(la) * math.sin(d) * math.cos(br))
    lo2 = lo + math.atan2(math.sin(br) * math.sin(d) * math.cos(la),
                          math.cos(d) - math.sin(la) * math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180


def distance_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2 +
         math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def rel_bearing(from_heading, to_bearing):
    """Signed bearing relative to the nose: negative is left, positive right."""
    return (to_bearing - from_heading + 540) % 360 - 180


# ------------------------------------------------------------- formations
class Aircraft:
    def __init__(self, lat, lon, heading, wingspan_m, length_m):
        self.lat, self.lon = lat, lon
        self.heading = heading
        self.wingspan = wingspan_m
        self.length = length_m

    @property
    def radius(self):
        """Half the biggest dimension — the circle the aircraft sits inside."""
        return max(self.wingspan, self.length) / 2.0


# Each entry is (bearing relative to the nose, distance as a multiple of the
# aircraft radius). Negative bearing is the left (port) side.
#
# Fire crews stand off the nose quarters and the tail, clear of the wings and
# engines. The ambulance is the exception: it comes right in to the forward
# left door, because that is where the patient comes out.
FORMATIONS = {
    'fire':     [(-45.0, 1.30), (45.0, 1.30), (180.0, 1.20)],
    'medical':  [(-78.0, 0.42)],
    # Police were standing off at 1.40 radii - about 47 m on an A350, which
    # read as "driving past and parking miles away". They should be up at the
    # aircraft like the ambulance: two on the door side, one off the nose.
    # Angles spread ~70 deg apart: on a small airframe the close-in floor
    # collapses them all to the same radius, so the ANGLE is what stops them
    # bunching into each other. Caught by the spacing test on an A320.
    'police':   [(-45.0, 0.55), (-115.0, 0.50), (175.0, 0.60)],
    'standby':  [(-60.0, 1.80), (60.0, 1.80)],
}

# Services allowed inside the aircraft's circle, because they attend the
# aircraft itself rather than standing clear of it.
CLOSE_IN = {'medical', 'police'}

# A close-in vehicle still must not end up inside the fuselage.
MIN_CLOSE_M = 10.0

MIN_MARGIN_M = 8.0          # never closer than this to the aircraft skin

# A stand-off service must be placed at least this many aircraft-radii out.
# The runtime clamp below would silently rescue a smaller number, which is
# exactly the problem: the vehicle would end up somewhere other than where the
# table says, and nothing would complain. So the table is checked on import.
MIN_STANDOFF_FACTOR = 1.15


def validate_formations():
    """Fail loudly on a nonsense formation rather than quietly clamping it."""
    bad = []
    for service, spots in FORMATIONS.items():
        if service in CLOSE_IN:
            continue
        for rel, factor in spots:
            if factor < MIN_STANDOFF_FACTOR:
                bad.append('%s at %+.0f deg has factor %.2f (min %.2f)'
                           % (service, rel, factor, MIN_STANDOFF_FACTOR))
    if bad:
        raise ValueError('formation would put vehicles into the airframe:\n  '
                         + '\n  '.join(bad))


def park_spots(ac, service):
    """Where each vehicle of `service` should end up. Returns [(lat, lon, heading)].

    Each vehicle faces the aircraft, which is both what actually happens and
    what stops them looking like they have been dropped in at random.
    """
    out = []
    for rel, factor in FORMATIONS[service]:
        dist = ac.radius * factor
        if service not in CLOSE_IN:
            # safety net for genuinely small aircraft, where a percentage of a
            # tiny radius is still too close. NOT a licence for a bad table -
            # validate_formations() catches that case separately.
            dist = max(dist, ac.radius + MIN_MARGIN_M)
        else:
            dist = max(dist, MIN_CLOSE_M)
        brg = (ac.heading + rel) % 360
        lat, lon = destination(ac.lat, ac.lon, brg, dist)
        facing = (brg + 180.0) % 360        # look back at the aircraft
        out.append((lat, lon, facing))
    return out


def clears_airframe(ac, lat, lon):
    """Is this point outside the circle the aircraft occupies, plus margin?"""
    return distance_m(ac.lat, ac.lon, lat, lon) >= ac.radius + MIN_MARGIN_M - 1e-6


def is_forward_of_wing(ac, lat, lon):
    """Is this point ahead of the aircraft's midpoint — i.e. not under a wing?"""
    b = bearing_deg(ac.lat, ac.lon, lat, lon)
    return abs(rel_bearing(ac.heading, b)) < 90.0


# ---------------------------------------------------------------- driving
class Vehicle:
    """A vehicle that drives to a point instead of teleporting to it.

    Speed and turn rate are capped so it looks like a vehicle rather than a
    cursor. Position is only ever advanced by `step`, so the caller cannot
    accidentally jump it across the airport.
    """

    def __init__(self, lat, lon, heading, max_speed_ms=11.0,
                 accel_ms2=2.5, turn_rate_deg_s=45.0):
        self.lat, self.lon, self.heading = lat, lon, heading
        self.speed = 0.0
        self.max_speed = max_speed_ms
        self.accel = accel_ms2
        self.turn_rate = turn_rate_deg_s
        self.arrived = False

    def step(self, dt, tgt_lat, tgt_lon, stop_within_m=2.0):
        d = distance_m(self.lat, self.lon, tgt_lat, tgt_lon)
        if d <= stop_within_m:
            self.speed = 0.0
            self.arrived = True
            return

        want = bearing_deg(self.lat, self.lon, tgt_lat, tgt_lon)
        err = rel_bearing(self.heading, want)
        turn = max(-self.turn_rate * dt, min(self.turn_rate * dt, err))
        self.heading = (self.heading + turn) % 360

        # slow down for the last stretch so it stops on the mark, and don't
        # accelerate hard while still swinging round onto the heading
        brake = min(1.0, d / 25.0)
        straight = max(0.25, 1.0 - abs(err) / 90.0)
        target_speed = self.max_speed * brake * straight
        if self.speed < target_speed:
            self.speed = min(target_speed, self.speed + self.accel * dt)
        else:
            self.speed = max(target_speed, self.speed - self.accel * 2 * dt)

        self.lat, self.lon = destination(self.lat, self.lon,
                                         self.heading, self.speed * dt)


def drive(vehicle, tgt_lat, tgt_lon, dt=0.1, max_seconds=600):
    """Run a vehicle to its target. Returns (seconds, path_length_m)."""
    t = 0.0
    travelled = 0.0
    while not vehicle.arrived and t < max_seconds:
        plat, plon = vehicle.lat, vehicle.lon
        vehicle.step(dt, tgt_lat, tgt_lon)
        travelled += distance_m(plat, plon, vehicle.lat, vehicle.lon)
        t += dt
    return t, travelled
