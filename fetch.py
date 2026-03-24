import json
import re
import time
import urllib.request
import urllib.parse
import os

PREFIX = "oney thing"

QUERIES_BY_YEAR = {
    "1234": """
"""
}
SERVERS =[
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.atownsend.org.uk/api/",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.maprva.org/api/",
    "https://overpass.private.coffee/api/interpreter"
]

RANK = {
    "province": 1, "state": 1,
    "district": 2, "county": 2,
    "municipality": 3, "city": 3,
    "town": 4,
    "village": 5, "hamlet": 5, "isolated_dwelling": 5,
    "suburb": 6, "quarter": 6,
    "neighbourhood": 7, "allotments": 7,
}
script_dir = os.path.dirname(os.path.abspath(__file__))

def load_queries(text):
    lines =[l for l in text.splitlines() if not l.strip().startswith("//")]
    blocks = re.split(r'(?=\[out:json\])', "\n".join(lines))
    return[b.strip() for b in blocks if b.strip()]

def fetch(query):
    timeout = int((re.search(r'\[timeout:(\d+)\]', query) or type('',(),{'group':lambda s,x:'600'})()).group(1)) + 30
    data = urllib.parse.urlencode({"data": query}).encode()
    for server in SERVERS:
        wait = 15
        for attempt in range(4):
            try:
                print(f"  -> {server}", flush=True)
                req = urllib.request.Request(server, data=data, headers={"User-Agent": "BORDMET-EXTRAPOLATOR/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    print(f"  ! 429 — waiting {wait}s", flush=True)
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                else:
                    break
            except Exception as e:
                break
    raise RuntimeError("all servers failed")

PREFERRED_LOCALES = ["fra", "fr","eng","en"] 
def standardize_to_poly_string(text):
    text = text.strip()
    if "[out:json]" in text:
        return text 

    nums = re.findall(r"(-?\d+(?:\.\d+)?)", text)
    
    if not nums:
        return None

    if len(nums) % 2 != 0:
        nums = nums[:-1]
        
    poly_parts = []
    for i in range(0, len(nums), 2):
        lon = nums[i]
        lat = nums[i+1]
        poly_parts.append(f"{lat} {lon}")
        
    return " ".join(poly_parts)

def get_4_bands(poly_coords):
    if "[out:json]" in poly_coords:
        return poly_coords

    bands = [
        f'[out:json][timeout:120];(node["place"~"^(region|province|state|district|county)$"](poly:"{poly_coords}");relation["place"~"^(region|province|state|district|county)$"](poly:"{poly_coords}"););out tags center;',
        f'[out:json][timeout:180];(node["place"~"^(municipality|city|town)$"](poly:"{poly_coords}");relation["place"~"^(municipality|city|town)$"](poly:"{poly_coords}"););out tags center;',
        f'[out:json][timeout:300];(node["place"~"^(village|hamlet|isolated_dwelling)$"](poly:"{poly_coords}");relation["place"~"^(village|hamlet|isolated_dwelling)$"](poly:"{poly_coords}"););out tags center;',
        f'[out:json][timeout:600];(node["place"~"^(suburb|quarter|neighbourhood|allotments)$"](poly:"{poly_coords}");relation["place"~"^(suburb|quarter|neighbourhood|allotments)$"](poly:"{poly_coords}"););out tags center;'
    ]
    return "\n\n".join(bands)

script_dir = os.path.dirname(os.path.abspath(__file__))

for year, raw_input in QUERIES_BY_YEAR.items():
    poly_string = standardize_to_poly_string(raw_input)
    if not poly_string:
        print(f"Skipping {year}: No coordinates found.")
        continue

    query_text = get_4_bands(poly_string)
    output_filename = f"{PREFIX}{year}.json"
    output_path = os.path.join(script_dir, output_filename)
    
    print(f"\n{'='*30}\nYEAR: {year} -> {output_filename}\n{'='*30}")
    
    all_places = []
    seen = set()
    
    for idx, query in enumerate(load_queries(query_text)):

        types = (re.search(r'\["place"~"\^\(([^)]+)\)\$"\]', query) or type('',(),{'group':lambda s,x:''})()).group(1)
        print(f"\n[BAND {idx+1} — {types}]", flush=True)
        
        if idx > 0: time.sleep(5)
        t0 = time.time()
        
        try:
            result = fetch(query)
        except RuntimeError as e:
            print(f"  SKIPPED: {e}", flush=True)
            continue
            
        new = 0
        for el in result.get("elements", []):
            tags = el.get("tags", {})
            
            name = None
            for lang in PREFERRED_LOCALES:
                if f"name:{lang}" in tags:
                    name = tags[f"name:{lang}"]
                    break
            
            if not name:
                name = tags.get("name") or tags.get("name:en")
                
            place = tags.get("place", "")
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            
            if not name or lat is None or lon is None: continue
            key = (name.lower(), place)
            if key in seen: continue
            seen.add(key)
            
            all_places.append({
                "name": name, 
                "place": place, 
                "rank": RANK.get(place, 9), 
                "coordinates": [round(float(lat), 7), round(float(lon), 7)]
            })
            new += 1
            
        print(f"  {new} new  ({time.time()-t0:.1f}s)", flush=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sorted(all_places, key=lambda x: x["rank"]), f, ensure_ascii=False, indent=2)
    print(f"\nDone with {year}. Saved {len(all_places)} places to {output_filename}")
