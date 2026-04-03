from flask import Flask, request, jsonify
from flask_cors import CORS
from immanuel import charts
from geopy.geocoders import Nominatim
import certifi
import ssl
import datetime
import os

app = Flask(__name__)
CORS(app)

# ── Gate wheel ────────────────────────────────────────────────────────────────
# 64 gates in zodiac order starting at 2° Aries; each gate = 5.625°
HD_GATES = [
    41, 19, 13, 49, 30, 55, 37, 63, 22, 36, 25, 17, 21, 51, 42,  3,
    27, 24,  2, 23,  8, 20, 16, 35, 45, 12, 15, 52, 39, 53, 62, 56,
    31, 33,  7,  4, 29, 59, 40, 64, 47,  6, 46, 18, 48, 57, 32, 50,
    28, 44,  1, 43, 14, 34,  9,  5, 26, 11, 10, 58, 38, 54, 61, 60,
]

# Opposite gate = 32 positions away (180°)
OPPOSITE_GATE = {HD_GATES[i]: HD_GATES[(i + 32) % 64] for i in range(64)}

# ── Channels ─────────────────────────────────────────────────────────────────
CHANNELS = [
    (frozenset({1,  8}),  ('G',            'Throat'      )),
    (frozenset({2,  14}), ('G',            'Sacral'      )),
    (frozenset({3,  60}), ('Sacral',       'Root'        )),
    (frozenset({4,  63}), ('Ajna',         'Head'        )),
    (frozenset({5,  15}), ('Sacral',       'G'           )),
    (frozenset({6,  59}), ('Solar Plexus', 'Sacral'      )),
    (frozenset({7,  31}), ('G',            'Throat'      )),
    (frozenset({9,  52}), ('Sacral',       'Root'        )),
    (frozenset({10, 20}), ('G',            'Throat'      )),
    (frozenset({10, 34}), ('G',            'Sacral'      )),
    (frozenset({11, 56}), ('Ajna',         'Throat'      )),
    (frozenset({12, 22}), ('Throat',       'Solar Plexus')),
    (frozenset({13, 33}), ('G',            'Throat'      )),
    (frozenset({16, 48}), ('Throat',       'Spleen'      )),
    (frozenset({17, 62}), ('Ajna',         'Throat'      )),
    (frozenset({18, 58}), ('Spleen',       'Root'        )),
    (frozenset({19, 49}), ('Root',         'Solar Plexus')),
    (frozenset({20, 57}), ('Throat',       'Spleen'      )),
    (frozenset({21, 45}), ('Heart',        'Throat'      )),
    (frozenset({23, 43}), ('Throat',       'Ajna'        )),
    (frozenset({24, 61}), ('Ajna',         'Head'        )),
    (frozenset({25, 51}), ('G',            'Heart'       )),
    (frozenset({26, 44}), ('Heart',        'Spleen'      )),
    (frozenset({27, 50}), ('Sacral',       'Spleen'      )),
    (frozenset({28, 38}), ('Spleen',       'Root'        )),
    (frozenset({29, 46}), ('Sacral',       'G'           )),
    (frozenset({30, 41}), ('Solar Plexus', 'Root'        )),
    (frozenset({32, 54}), ('Spleen',       'Root'        )),
    (frozenset({34, 20}), ('Sacral',       'Throat'      )),
    (frozenset({34, 57}), ('Sacral',       'Spleen'      )),
    (frozenset({35, 36}), ('Throat',       'Solar Plexus')),
    (frozenset({37, 40}), ('Solar Plexus', 'Heart'       )),
    (frozenset({39, 55}), ('Root',         'Solar Plexus')),
    (frozenset({42, 53}), ('Sacral',       'Root'        )),
    (frozenset({47, 64}), ('Ajna',         'Head'        )),
    (frozenset({63,  4}), ('Head',         'Ajna'        )),
]

MOTORS = {'Sacral', 'Heart', 'Solar Plexus', 'Root'}

HD_PLANETS = {
    'Sun', 'Moon', 'Mercury', 'Venus', 'Mars',
    'Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto',
    'True North Node', 'True South Node',
}

# ── Cross names keyed by gate (both gates in each axis pair share the name) ──
GATE_TO_CROSS_NAME = {
    1: 'the Sphinx',           2: 'the Sphinx',
    3: 'Mutation',            50: 'Mutation',
    4: 'Explanation',         49: 'Explanation',
    5: 'Contagion',           35: 'Contagion',
    6: 'Conflict',            36: 'Conflict',
    7: 'Interaction',         13: 'Interaction',
    8: 'Service',             14: 'Service',
    9: 'Identification',      16: 'Identification',
   10: 'the Vessel of Love',  15: 'the Vessel of Love',
   11: 'Eden',                12: 'Eden',
   17: 'the Sleeping Phoenix',18: 'the Sleeping Phoenix',
   19: 'Contagion',           33: 'Contagion',
   20: 'Maya',                34: 'Maya',
   21: 'the Four Ways',       48: 'the Four Ways',
   22: 'Grace',               47: 'Grace',
   23: 'Structuring',         43: 'Structuring',
   24: 'the Market',          44: 'the Market',
   25: 'Perfected Form',      46: 'Perfected Form',
   26: 'the Industry',        45: 'the Industry',
   27: 'Caring',              28: 'Caring',
   29: 'Commitment',          30: 'Commitment',
   31: 'the Alpha',           41: 'the Alpha',
   32: 'Variation',           42: 'Variation',
   37: 'the Community',       40: 'the Community',
   38: 'Opposition',          39: 'Opposition',
   51: 'Penetration',         57: 'Penetration',
   52: 'Stillness',           58: 'Stillness',
   53: 'Cycles',              54: 'Cycles',
   55: 'Dominion',            59: 'Dominion',
   56: 'Limitation',          60: 'Limitation',
   61: 'Consciousness',       62: 'Consciousness',
   63: 'Confusion',           64: 'Confusion',
}


# ── Core helpers ──────────────────────────────────────────────────────────────

def lon_to_gate_line(lon: float) -> tuple[int, int]:
    adjusted = (lon - 2.0) % 360.0
    idx = int(adjusted / 5.625)
    gate = HD_GATES[min(idx, 63)]
    within = adjusted - idx * 5.625
    line = min(int(within / 0.9375) + 1, 6)
    return gate, line


def get_chart_data(birth_dt: datetime.datetime, lat: float, lon: float):
    """Return (active_gates, personality_sun, design_sun) where sun = (gate, line)."""
    design_dt = birth_dt - datetime.timedelta(days=88.736)
    active_gates: set[int] = set()
    personality_sun = design_sun = None

    for i, dt in enumerate([birth_dt, design_dt]):
        is_personality = (i == 0)
        subject = charts.Subject(date_time=dt, latitude=lat, longitude=lon)
        chart = charts.Natal(subject)

        for _, obj in chart.objects.items():
            if obj.name not in HD_PLANETS:
                continue
            raw_lon = obj.longitude.raw
            gate, line = lon_to_gate_line(raw_lon)
            active_gates.add(gate)

            if obj.name == 'Sun':
                if is_personality:
                    personality_sun = (gate, line)
                else:
                    design_sun = (gate, line)
                # Earth = opposite Sun
                active_gates.add(lon_to_gate_line((raw_lon + 180.0) % 360.0)[0])

    return active_gates, personality_sun, design_sun


def analyze_centers(active_gates: set[int]):
    """Return (defined_centers, active_channel_pairs)."""
    active_pairs = []
    defined: set[str] = set()
    for gate_set, (c1, c2) in CHANNELS:
        if gate_set.issubset(active_gates):
            active_pairs.append((c1, c2))
            defined.add(c1)
            defined.add(c2)
    return defined, active_pairs


def get_hd_type(defined: set[str], active_pairs: list) -> str:
    if not defined:
        return 'Reflector'

    adj: dict[str, set[str]] = {}
    for c1, c2 in active_pairs:
        adj.setdefault(c1, set()).add(c2)
        adj.setdefault(c2, set()).add(c1)

    motor_to_throat = False
    if 'Throat' in defined:
        for motor in MOTORS:
            if motor not in adj:
                continue
            visited: set[str] = set()
            queue = [motor]
            while queue:
                node = queue.pop()
                if node == 'Throat':
                    motor_to_throat = True
                    break
                if node in visited:
                    continue
                visited.add(node)
                queue.extend(adj.get(node, []))
            if motor_to_throat:
                break

    sacral = 'Sacral' in defined
    if sacral and motor_to_throat:
        return 'Manifesting Generator'
    if sacral:
        return 'Generator'
    if motor_to_throat:
        return 'Manifestor'
    return 'Projector'


def get_authority(defined: set[str], active_pairs: list) -> str:
    if not defined:
        return 'Lunar'
    direct: dict[str, set[str]] = {}
    for c1, c2 in active_pairs:
        direct.setdefault(c1, set()).add(c2)
        direct.setdefault(c2, set()).add(c1)

    if 'Solar Plexus' in defined:
        return 'Emotional / Solar Plexus'
    if 'Sacral' in defined:
        return 'Sacral'
    if 'Spleen' in defined:
        return 'Splenic'
    if 'Heart' in defined:
        if 'Throat' in direct.get('Heart', set()):
            return 'Ego Manifested'
        return 'Ego Projected'
    if 'G' in defined and 'Throat' in direct.get('G', set()):
        return 'Self-Projected'
    return 'Mental / No Inner Authority'


def get_definition(defined: set[str], active_pairs: list) -> str:
    if not defined:
        return 'Single'
    parent = {c: c for c in defined}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c1, c2 in active_pairs:
        px, py = find(c1), find(c2)
        if px != py:
            parent[px] = py

    count = len({find(c) for c in defined})
    return {1: 'Single', 2: 'Split', 3: 'Triple Split', 4: 'Quadruple Split'}.get(count, f'{count}-way Split')


def get_incarnation_cross(cs_gate: int, cs_line: int, us_gate: int) -> str:
    ce_gate = OPPOSITE_GATE[cs_gate]
    ue_gate = OPPOSITE_GATE[us_gate]

    if cs_line <= 3:
        angle = 'Right Angle'
    elif cs_line == 4:
        angle = 'Juxtaposition'
    else:
        angle = 'Left Angle'

    name = GATE_TO_CROSS_NAME.get(cs_gate, f'Gate {cs_gate}')
    return f"{angle} Cross of {name} ({cs_gate}/{ce_gate} | {us_gate}/{ue_gate})"


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.route('/chart', methods=['POST'])
def chart():
    data = request.get_json(force=True)
    birth_date = data.get('birth_date')
    birth_time = data.get('birth_time')
    birth_city = data.get('birth_city')

    if not all([birth_date, birth_time, birth_city]):
        return jsonify({'error': 'birth_date, birth_time, and birth_city are required'}), 400

    try:
        birth_dt = datetime.datetime.strptime(f'{birth_date} {birth_time}', '%Y-%m-%d %H:%M')
    except ValueError as e:
        return jsonify({'error': f'Invalid date/time format: {e}'}), 400

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    geolocator = Nominatim(user_agent='hd-chart-api', ssl_context=ssl_ctx)
    location = geolocator.geocode(birth_city)
    if not location:
        return jsonify({'error': f'Could not geocode city: {birth_city}'}), 400

    lat, lon = location.latitude, location.longitude
    active_gates, personality_sun, design_sun = get_chart_data(birth_dt, lat, lon)

    defined, active_pairs = analyze_centers(active_gates)

    cs_gate, cs_line = personality_sun
    us_gate, us_line = design_sun

    return jsonify({
        'human_design_type':  get_hd_type(defined, active_pairs),
        'profile':            f'{cs_line}/{us_line}',
        'authority':          get_authority(defined, active_pairs),
        'definition':         get_definition(defined, active_pairs),
        'defined_centers':    sorted(defined),
        'incarnation_cross':  get_incarnation_cross(cs_gate, cs_line, us_gate),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
