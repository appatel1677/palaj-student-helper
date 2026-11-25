import os
import re
import io
import json
import math
import urllib.request
import urllib.parse
from db_and_pdf import get_pdf_font

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib import font_manager
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

_GEO_MEM_CACHE = {}

GUJ_DIST_KEYWORDS = {
    "મહેસાણા": ("મહેસાણા", "Mehsana district, Gujarat, India"),
    "mahesana": ("મહેસાણા", "Mehsana district, Gujarat, India"),
    "mehsana": ("મહેસાણા", "Mehsana district, Gujarat, India"),
    "બનાસકાંઠા": ("બનાસકાંઠા", "Banaskantha district, Gujarat, India"),
    "banaskantha": ("બનાસકાંઠા", "Banaskantha district, Gujarat, India"),
    "પાટણ": ("પાટણ", "Patan district, Gujarat, India"),
    "patan": ("પાટણ", "Patan district, Gujarat, India"),
    "કચ્છ": ("કચ્છ", "Kutch district, Gujarat, India"),
    "kutch": ("કચ્છ", "Kutch district, Gujarat, India"),
    "સાબરકાંઠા": ("સાબરકાંઠા", "Sabarkantha district, Gujarat, India"),
    "sabarkantha": ("સાબરકાંઠા", "Sabarkantha district, Gujarat, India"),
    "અરવલ્લી": ("અરવલ્લી", "Aravalli district, Gujarat, India"),
    "aravalli": ("અરવલ્લી", "Aravalli district, Gujarat, India"),
    "ગાંધીનગર": ("ગાંધીનગર", "Gandhinagar district, Gujarat, India"),
    "gandhinagar": ("ગાંધીનગર", "Gandhinagar district, Gujarat, India"),
    "અમદાવાદ": ("અમદાવાદ", "Ahmedabad district, Gujarat, India"),
    "ahmedabad": ("અમદાવાદ", "Ahmedabad district, Gujarat, India"),
    "ખેડા": ("ખેડા", "Kheda district, Gujarat, India"),
    "kheda": ("ખેડા", "Kheda district, Gujarat, India"),
    "આણંદ": ("આણંદ", "Anand district, Gujarat, India"),
    "anand": ("આણંદ", "Anand district, Gujarat, India"),
    "વડોદરા": ("વડોદરા", "Vadodara district, Gujarat, India"),
    "vadodara": ("વડોદરા", "Vadodara district, Gujarat, India"),
    "સુરત": ("સુરત", "Surat district, Gujarat, India"),
    "surat": ("સુરત", "Surat district, Gujarat, India"),
    "ભરૂચ": ("ભરૂચ", "Bharuch district, Gujarat, India"),
    "bharuch": ("ભરૂચ", "Bharuch district, Gujarat, India"),
    "નર્મદા": ("નર્મદા", "Narmada district, Gujarat, India"),
    "narmada": ("નર્મદા", "Narmada district, Gujarat, India"),
    "વલસાડ": ("વલસાડ", "Valsad district, Gujarat, India"),
    "valsad": ("વલસાડ", "Valsad district, Gujarat, India"),
    "નવસારી": ("નવસારી", "Navsari district, Gujarat, India"),
    "navsari": ("નવસારી", "Navsari district, Gujarat, India"),
    "ડાંગ": ("ડાંગ", "Dang district, Gujarat, India"),
    "dang": ("ડાંગ", "Dang district, Gujarat, India"),
    "રાજકોટ": ("રાજકોટ", "Rajkot district, Gujarat, India"),
    "rajkot": ("રાજકોટ", "Rajkot district, Gujarat, India"),
    "જામનગર": ("જામનગર", "Jamnagar district, Gujarat, India"),
    "jamnagar": ("જામનગર", "Jamnagar district, Gujarat, India"),
    "જૂનાગઢ": ("જૂનાગઢ", "Junagadh district, Gujarat, India"),
    "junagadh": ("જૂનાગઢ", "Junagadh district, Gujarat, India"),
    "ભાવનગર": ("ભાવનગર", "Bhavnagar district, Gujarat, India"),
    "bhavnagar": ("ભાવનગર", "Bhavnagar district, Gujarat, India"),
    "અમરેલી": ("અમરેલી", "Amreli district, Gujarat, India"),
    "amreli": ("અમરેલી", "Amreli district, Gujarat, India"),
    "મોરબી": ("મોરબી", "Morbi district, Gujarat, India"),
    "morbi": ("મોરબી", "Morbi district, Gujarat, India"),
    "સુરેન્દ્રનગર": ("સુરેન્દ્રનગર", "Surendranagar district, Gujarat, India"),
    "surendranagar": ("સુરેન્દ્રનગર", "Surendranagar district, Gujarat, India"),
    "પોરબંદર": ("પોરબંદર", "Porbandar district, Gujarat, India"),
    "porbandar": ("પોરબંદર", "Porbandar district, Gujarat, India"),
    "ગીર સોમનાથ": ("ગીર સોમનાથ", "Gir Somnath district, Gujarat, India"),
    "gir somnath": ("ગીર સોમનાથ", "Gir Somnath district, Gujarat, India"),
    "દેવભૂમિ દ્વારકા": ("દેવભૂમિ દ્વારકા", "Devbhoomi Dwarka district, Gujarat, India"),
    "dwarka": ("દેવભૂમિ દ્વારકા", "Devbhoomi Dwarka district, Gujarat, India"),
    "બોટાદ": ("બોટાદ", "Botad district, Gujarat, India"),
    "botad": ("બોટાદ", "Botad district, Gujarat, India"),
    "મહીસાગર": ("મહીસાગર", "Mahisagar district, Gujarat, India"),
    "mahisagar": ("મહીસાગર", "Mahisagar district, Gujarat, India"),
    "પંચમહાલ": ("પંચમહાલ", "Panchmahal district, Gujarat, India"),
    "panchmahal": ("પંચમહાલ", "Panchmahal district, Gujarat, India"),
    "દાહોદ": ("દાહોદ", "Dahod district, Gujarat, India"),
    "dahod": ("દાહોદ", "Dahod district, Gujarat, India"),
    "છોટા ઉદેપુર": ("છોટા ઉદેપુર", "Chhota Udaipur district, Gujarat, India"),
    "chhota udaipur": ("છોટા ઉદેપુર", "Chhota Udaipur district, Gujarat, India"),
    "તાપી": ("તાપી", "Tapi district, Gujarat, India"),
    "tapi": ("તાપી", "Tapi district, Gujarat, India"),
}

DISTRICT_BUILTIN_PINS = {
    "મહેસાણા": [
        {"name": "મહેસાણા", "lon": 72.3693, "lat": 23.5880, "type": "taluka"},
        {"name": "વિસનગર", "lon": 72.5522, "lat": 23.6987, "type": "taluka"},
        {"name": "ઊંઝા", "lon": 72.3912, "lat": 23.8037, "type": "taluka"},
        {"name": "કડી", "lon": 72.3336, "lat": 23.2991, "type": "taluka"},
        {"name": "ખેરાલુ", "lon": 72.6133, "lat": 23.8861, "type": "taluka"},
        {"name": "વડનગર", "lon": 72.6331, "lat": 23.7852, "type": "taluka"},
        {"name": "વિજાપુર", "lon": 72.7525, "lat": 23.5612, "type": "taluka"},
        {"name": "બેચરાજી", "lon": 72.0461, "lat": 23.5015, "type": "taluka"},
        {"name": "સતલાસણા", "lon": 72.7358, "lat": 24.0061, "type": "taluka"},
        {"name": "જોટાણા", "lon": 72.3168, "lat": 23.4756, "type": "taluka"},
        {"name": "પલાજ", "lon": 72.4265, "lat": 23.5535, "type": "village"},
        {"name": "મોઢેરા", "lon": 72.1332, "lat": 23.5835, "type": "village"},
        {"name": "તારંગા", "lon": 72.7562, "lat": 23.9631, "type": "village"},
        {"name": "લાંઘણજ", "lon": 72.4950, "lat": 23.4520, "type": "village"},
        {"name": "ગોઝારિયા", "lon": 72.6010, "lat": 23.4890, "type": "village"},
        {"name": "આંબલિયાસણ", "lon": 72.4410, "lat": 23.4830, "type": "village"},
        {"name": "ઉનાવા", "lon": 72.3735, "lat": 23.7580, "type": "village"},
        {"name": "ભાંડુ", "lon": 72.3780, "lat": 23.6940, "type": "village"},
        {"name": "નંદાસણ", "lon": 72.4110, "lat": 23.3820, "type": "village"},
        {"name": "સુંઢિયા", "lon": 72.5780, "lat": 23.8210, "type": "village"},
        {"name": "કુકસ", "lon": 72.4150, "lat": 23.6350, "type": "village"},
        {"name": "લડાલ", "lon": 72.6850, "lat": 23.6320, "type": "village"},
    ],
    "પાટણ": [
        {"name": "પાટણ", "lon": 72.1266, "lat": 23.8493, "type": "taluka"},
        {"name": "સિદ્ધપુર", "lon": 72.3736, "lat": 23.9182, "type": "taluka"},
        {"name": "ચાણસ્મા", "lon": 72.1211, "lat": 23.7192, "type": "taluka"},
        {"name": "હારિજ", "lon": 71.8981, "lat": 23.6942, "type": "taluka"},
        {"name": "સમી", "lon": 71.7891, "lat": 23.6881, "type": "taluka"},
        {"name": "રાધનપુર", "lon": 71.6067, "lat": 23.8315, "type": "taluka"},
        {"name": "સાંતલપુર", "lon": 71.1892, "lat": 23.7765, "type": "taluka"},
        {"name": "સરસ્વતી", "lon": 72.0750, "lat": 23.8850, "type": "taluka"},
        {"name": "શંખેશ્વર", "lon": 71.7850, "lat": 23.5150, "type": "taluka"},
        {"name": "રાણીની વાવ", "lon": 72.1018, "lat": 23.8589, "type": "village"},
        {"name": "વરણા", "lon": 72.1550, "lat": 23.9050, "type": "village"},
        {"name": "ખાનપુર", "lon": 72.0550, "lat": 23.7950, "type": "village"},
    ]
}

OFFLINE_DISTRICT_POLYGONS = {
    "મહેસાણા": [
        [71.95, 23.45], [72.02, 23.62], [72.22, 23.68], [72.32, 23.85],
        [72.52, 23.95], [72.72, 24.08], [72.83, 23.96], [72.78, 23.78],
        [72.82, 23.54], [72.66, 23.44], [72.48, 23.36], [72.38, 23.21],
        [72.22, 23.25], [72.18, 23.40], [71.95, 23.45]
    ],
    "પાટણ": [
        [71.05, 23.72], [71.22, 23.96], [71.65, 24.00], [72.02, 24.00],
        [72.44, 24.03], [72.48, 23.86], [72.26, 23.72], [72.18, 23.62],
        [71.92, 23.44], [71.68, 23.47], [71.50, 23.65], [71.12, 23.62], [71.05, 23.72]
    ]
}

DISTRICT_EN_TO_GUJ = {
    "kachchh": ("કચ્છ", "kutch"), "kutch": ("કચ્છ", "kutch"),
    "banaskantha": ("બનાસકાંઠા", "north"), "banas kantha": ("બનાસકાંઠા", "north"),
    "patan": ("પાટણ", "north"),
    "mahesana": ("મહેસાણા", "north"), "mehsana": ("મહેસાણા", "north"),
    "sabarkantha": ("સાબરકાંઠા", "north"), "sabar kantha": ("સાબરકાંઠા", "north"),
    "aravalli": ("અરવલ્લી", "north"), "arvalli": ("અરવલ્લી", "north"),
    "gandhinagar": ("ગાંધીનગર", "central"),
    "ahmadabad": ("અમદાવાદ", "central"), "ahmedabad": ("અમદાવાદ", "central"),
    "kheda": ("ખેડા", "central"),
    "mahisagar": ("મહીસાગર", "central"),
    "panchmahal": ("પંચમહાલ", "central"), "panch mahals": ("પંચમહાલ", "central"),
    "dohad": ("દાહોદ", "central"), "dahod": ("દાહોદ", "central"),
    "anand": ("આણંદ", "central"),
    "vadodara": ("વડોદરા", "central"),
    "chhotaudepur": ("છોટા ઉદેપુર", "central"), "chhota udaipur": ("છોટા ઉદેપુર", "central"),
    "bharuch": ("ભરૂચ", "south"),
    "narmada": ("નર્મદા", "south"),
    "surat": ("સુરત", "south"),
    "tapi": ("તાપી", "south"),
    "navsari": ("નવસારી", "south"),
    "the dangs": ("ડાંગ", "south"), "dang": ("ડાંગ", "south"), "dangs": ("ડાંગ", "south"),
    "valsad": ("વલસાડ", "south"),
    "surendranagar": ("સુરેન્દ્રનગર", "saurashtra"),
    "morbi": ("મોરબી", "saurashtra"),
    "jamnagar": ("જામનગર", "saurashtra"),
    "devbhumi dwarka": ("દેવભૂમિ દ્વારકા", "saurashtra"), "dwarka": ("દેવભૂમિ દ્વારકા", "saurashtra"),
    "porbandar": ("પોરબંદર", "saurashtra"),
    "rajkot": ("રાજકોટ", "saurashtra"),
    "botad": ("બોટાદ", "saurashtra"),
    "junagadh": ("જૂનાગઢ", "saurashtra"),
    "amreli": ("અમરેલી", "saurashtra"),
    "bhavnagar": ("ભાવનગર", "saurashtra"),
    "gir somnath": ("
