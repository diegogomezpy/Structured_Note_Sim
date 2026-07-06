"""
app/cover_photos.py
-------------------
The industry cover-photo taxonomy (sector -> Pexels search terms, plus the
Yahoo sector/industry -> library-sector maps). Pure data + it belongs beside
the other framework-free app/ helpers, not in the FastAPI routing layer.
api/main.py imports these; the Pexels network calls + routes stay there.
"""
from __future__ import annotations


SECTOR_QUERIES: "dict[str, list[str]]" = {
    "technology":         ["server room data center", "microchip processor macro", "circuit board electronics",
                           "robotic arm automation", "fiber optic network", "programmer coding screens",
                           "semiconductor clean room", "futuristic technology"],
    "energy":             ["oil refinery at night", "offshore wind turbines", "solar farm aerial",
                           "power plant cooling towers", "oil drilling rig", "hydroelectric dam",
                           "natural gas pipeline", "electricity pylons sunset"],
    "financials":         ["stock exchange trading floor", "financial district skyscrapers", "bank building columns",
                           "stock market charts screen", "gold bullion bars", "business handshake deal",
                           "wall street", "money currency finance"],
    "healthcare":         ["pharmaceutical research lab", "modern hospital corridor", "dna double helix",
                           "surgeons operating room", "medicine pills macro", "microscope laboratory",
                           "mri scanner machine", "scientist vaccine research"],
    "consumer_cyclical":  ["luxury retail boutique", "automobile assembly line", "shopping mall interior",
                           "fashion clothing store", "restaurant fine dining", "ecommerce delivery packages",
                           "car showroom", "travel resort hotel"],
    "consumer_defensive": ["supermarket shelves", "fresh produce market", "packaged food factory",
                           "beverage bottling line", "household cleaning products", "grocery checkout",
                           "agriculture farm field", "warehouse stocked goods"],
    "industrials":        ["factory robotic assembly", "heavy construction machinery", "cargo container port",
                           "aircraft manufacturing", "industrial warehouse", "welding sparks metal",
                           "freight train cargo", "construction crane skyline"],
    "materials":          ["steel mill molten metal", "open pit mine", "copper smelting plant",
                           "chemical plant pipes", "lumber timber yard", "gold mining",
                           "cement factory", "raw minerals ore"],
    "utilities":          ["high voltage power lines", "electric power plant", "water treatment facility",
                           "nuclear cooling towers", "solar utility farm", "electrical substation",
                           "wind energy turbines", "hydroelectric dam reservoir"],
    "real_estate":        ["modern office tower glass", "city skyline aerial", "luxury apartment building",
                           "construction site crane", "suburban residential houses", "commercial building facade",
                           "real estate keys home", "industrial warehouse property"],
    "communication":      ["telecom broadcast tower", "5g antenna mast", "fiber network servers",
                           "television broadcast studio", "satellite dish array", "social media smartphone",
                           "undersea cable network", "media newsroom"],
    "defense":            ["fighter jet aircraft", "naval warship ocean", "military radar defense",
                           "army tank field", "missile launch defense", "military drone uav",
                           "soldiers formation march", "aircraft carrier deck"],
    "aerospace":          ["commercial jet takeoff", "aircraft assembly hangar", "rocket launch space",
                           "satellite in orbit", "airplane cockpit controls", "jet engine turbine",
                           "airport runway planes", "spacecraft engineering lab"],
    "transportation":     ["cargo container ship port", "freight train railway", "logistics warehouse trucks",
                           "highway trucks aerial", "shipping port cranes", "delivery van fleet",
                           "railway station tracks", "air cargo loading"],
    "automotive":         ["car assembly line robots", "electric vehicle charging", "automobile showroom",
                           "sports car studio", "car manufacturing factory", "ev battery production",
                           "automotive engine macro", "highway traffic cars"],
    "semiconductors":     ["silicon wafer macro", "semiconductor clean room", "microchip fabrication",
                           "computer processor macro", "chip manufacturing robot", "circuit board closeup",
                           "nanotechnology lab", "electronics production line"],
    "infrastructure":     ["bridge construction engineering", "highway overpass aerial", "construction crane megaproject",
                           "tunnel infrastructure", "dam engineering concrete", "skyscraper construction",
                           "roadworks machinery", "power grid infrastructure"],
    "agriculture":        ["wheat field harvest", "tractor plowing field", "modern greenhouse farming",
                           "vineyard aerial rows", "combine harvester", "irrigation crops field",
                           "livestock cattle farm", "grain silos storage"],
    "luxury":             ["luxury boutique storefront", "designer handbags display", "fine jewelry diamonds",
                           "luxury watch macro", "champagne celebration toast", "yacht ocean luxury",
                           "haute couture fashion runway", "luxury car detail"],
    "retail":             ["shopping mall interior", "retail store shelves", "ecommerce fulfillment center",
                           "checkout counter store", "clothing retail display", "supermarket aisle",
                           "shopping crowd store", "online shopping delivery"],
    "insurance":          ["insurance office handshake", "family home protection concept", "car accident claim",
                           "umbrella protection concept", "financial advisor meeting", "health insurance care",
                           "property insurance house", "risk management documents"],
    "banking":            ["bank branch interior", "atm banking machine", "bank vault safe",
                           "mobile banking phone", "credit card payment", "bank building facade",
                           "banker client meeting", "digital banking network"],
    "travel":             ["luxury resort pool", "airport terminal travelers", "tropical beach vacation",
                           "hotel lobby modern", "cruise ship ocean", "city tourism landmark",
                           "airplane window view", "mountain travel adventure"],
    "mining":             ["open pit mine aerial", "mining excavator machinery", "gold ore extraction",
                           "coal mining site", "copper mine terraces", "underground mine tunnel",
                           "mining haul truck", "raw mineral ore"],
    "cybersecurity":      ["cybersecurity data center", "digital lock security", "network security servers",
                           "code screen security", "biometric security scan", "encrypted data network",
                           "security operations center", "firewall network protection"],
    "renewables":         ["solar panel farm aerial", "wind turbine field", "clean energy sunset",
                           "hydroelectric power dam", "green energy technology", "battery storage renewable",
                           "geothermal power plant", "sustainable energy grid"],
    "media":              ["television broadcast studio", "film production set", "streaming media concept",
                           "newsroom journalists", "music recording studio", "cinema movie theater",
                           "live concert stage", "content creator studio"],
    "pharmaceuticals":    ["pharmaceutical production line", "vaccine research lab", "pill manufacturing macro",
                           "biotech laboratory scientist", "drug discovery microscope", "medical research dna",
                           "pharmacy medicine shelves", "clinical trial laboratory"],
    "markets":            ["stock market display board", "world map global finance", "candlestick trading charts",
                           "business district skyline", "currency exchange money", "economic data screens",
                           "bull and bear market", "financial newspaper"],
}
YAHOO_SECTOR_ALIAS = {
    "technology": "technology", "energy": "energy",
    "financial services": "financials", "financials": "financials", "financial": "financials",
    "healthcare": "healthcare", "health care": "healthcare",
    "consumer cyclical": "consumer_cyclical", "consumer discretionary": "consumer_cyclical",
    "consumer defensive": "consumer_defensive", "consumer staples": "consumer_defensive",
    "industrials": "industrials",
    "basic materials": "materials", "materials": "materials",
    "utilities": "utilities", "real estate": "real_estate",
    "communication services": "communication", "communication": "communication",
}
# Yahoo's coarse `sector` field only spans the ~11 GICS-style sectors above; the
# finer photo sectors (defense, semiconductors, luxury, banking, …) live in
# Yahoo's `industry` field. This maps an industry string (lowercased, substring
# match) → the specific photo sector, so auto-suggestion can reach the granular
# ones. Ordered specific → general (first hit wins). Dash-free needles sidestep
# Yahoo's inconsistent em-dash/hyphen use ("Banks—Regional" vs "Banks - Regional").
INDUSTRY_SECTOR_MAP: "list[tuple[str, str]]" = [
    ("aerospace", "aerospace"),                      # "Aerospace & Defense"
    ("defense", "defense"),
    ("semiconductor", "semiconductors"),             # incl. "…Equipment & Materials"
    ("drug manufacturers", "pharmaceuticals"),
    ("biotechnology", "pharmaceuticals"),
    ("luxury goods", "luxury"),
    ("banks", "banking"),
    ("insurance", "insurance"),
    ("railroads", "transportation"),
    ("trucking", "transportation"),
    ("freight", "transportation"),                   # "Integrated Freight & Logistics"
    ("marine shipping", "transportation"),
    ("airports", "transportation"),
    ("airlines", "travel"),
    ("travel services", "travel"),
    ("resorts", "travel"),                           # "Resorts & Casinos"
    ("lodging", "travel"),
    ("gold", "mining"),
    ("silver", "mining"),
    ("copper", "mining"),
    ("aluminum", "mining"),
    ("coal", "mining"),
    ("mining", "mining"),                            # "…& Mining"
    ("engineering & construction", "infrastructure"),
    ("infrastructure", "infrastructure"),
    ("solar", "renewables"),
    ("renewable", "renewables"),                     # "Utilities—Renewable"
    ("farm products", "agriculture"),
    ("agricultural", "agriculture"),                 # "Agricultural Inputs"
    ("auto manufacturers", "automotive"),
    ("auto parts", "automotive"),
    ("auto & truck", "automotive"),                  # "Auto & Truck Dealerships"
    ("entertainment", "media"),
    ("broadcasting", "media"),
    ("retail", "retail"),                            # generic retail after specifics
    ("stores", "retail"),                            # "Grocery/Discount/Department Stores"
]
