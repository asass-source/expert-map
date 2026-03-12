#!/usr/bin/env python3
"""Industry Expert Map — Fully dynamic FastAPI backend. No pre-loaded data.
Everything generated on demand via web search + LLM."""

import json
import os
import re
import traceback
import httpx
import hashlib
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
# Expert generation uses asyncio for parallel processing

# ============================================================
# DISK-PERSISTENT CACHE
# ============================================================
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

def _cache_path(prefix: str, key: str) -> Path:
    safe = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{prefix}_{safe}.json"

def disk_load(prefix: str, key: str):
    p = _cache_path(prefix, key)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return None

def disk_save(prefix: str, key: str, data):
    try:
        _cache_path(prefix, key).write_text(json.dumps(data, default=str))
    except Exception as e:
        print(f"[CACHE] disk_save failed: {e}")

# ============================================================
# IN-MEMORY CACHE (starts empty — everything generated on demand)
# ============================================================
company_cache: dict = {}     # ticker -> company profile dict
experts_cache: dict = {}     # ticker -> list of expert dicts
questions_cache: dict = {}   # "ticker:expert_id" -> list of questions
executives_cache: dict = {}  # ticker -> list of executive dicts
exec_experts_cache: dict = {} # "ticker:exec_name" -> list of experts
entity_experts_cache: dict = {} # "entity_name" -> list of experts
directory_experts_cache: dict = {} # ticker -> list of expert dicts (different from experts_cache)
next_expert_id = 1

def mem_or_disk(mem_cache: dict, prefix: str, key: str):
    """Check memory first, then disk. Returns data or None.
    Note: Returns empty lists/dicts too ([] means generation completed with no results)."""
    if key in mem_cache:
        val = mem_cache[key]
        if val is not None:  # None means 'not set'; [] means 'set but empty'
            return val
    data = disk_load(prefix, key)
    if data is not None:
        mem_cache[key] = data
        return data
    return None

def save_both(mem_cache: dict, prefix: str, key: str, data):
    """Save to both memory and disk."""
    mem_cache[key] = data
    disk_save(prefix, key, data)

# ============================================================
# BACKGROUND PREFETCH TRACKING
# ============================================================
# ticker -> { "status": "running"|"done", "exec_done": 3, "exec_total": 10, "entity_done": 5, "entity_total": 15, "questions_done": 2, "questions_total": 10 }
prefetch_status: dict = {}

# ============================================================
# WELL-KNOWN TICKERS (for search autocomplete only — no data pre-loaded)
# ============================================================
WELL_KNOWN_COMPANIES = {
    "A": "Agilent Technologies", "AA": "Alcoa Corp.", "AAL": "American Airlines Group Inc.",
    "AAMI": "Acadian Asset Management Inc.", "AAOI": "Applied Optoelectronics Inc.", "AAON": "Aaon Inc.",
    "AAP": "Advance Auto Parts Inc.", "AAPL": "Apple Inc.", "AAT": "American Assets Trust REIT Inc.",
    "ABAT": "American Battery Technology Compan", "ABBV": "AbbVie", "ABCB": "Ameris Bancorp",
    "ABG": "Asbury Automotive Group Inc.", "ABM": "Abm Industries Inc.", "ABNB": "Airbnb",
    "ABR": "Arbor Realty Trust REIT Inc.", "ABSI": "Absci Corp.", "ABT": "Abbott Laboratories",
    "ABUS": "Arbutus Biopharma Corp.", "ACA": "Arcosa Inc.", "ACAD": "Acadia Pharmaceuticals Inc.",
    "ACCO": "Acco Brands Corp.", "ACDC": "Profrac Holding Class A Corp.", "ACEL": "Accel Entertainment Inc. Class A",
    "ACGL": "Arch Capital Group", "ACH": "Accendra Health Inc.", "ACHC": "Acadia Healthcare Company Inc.",
    "ACHR": "Archer Aviation Inc. Class A", "ACI": "Albertsons Company Inc. Class A", "ACIC": "American Coastal Insurance Corp.",
    "ACIW": "Aci Worldwide Inc.", "ACLS": "Axcelis Technologies Inc.", "ACLX": "Arcellx Inc.",
    "ACM": "Aecom", "ACMR": "Acm Research Class A Inc.", "ACN": "Accenture",
    "ACNB": "Acnb Corp.", "ACRE": "Ares Commercial Real Estate REIT C", "ACT": "Enact Holdings Inc.",
    "ACTG": "Acacia Research Corp.", "ACVA": "Acv Auctions Inc. Class A", "ADAM": "Adamas Inc. Trust",
    "ADBE": "Adobe Inc.", "ADC": "Agree Realty REIT Corp.", "ADCT": "Adc Therapeutics SA",
    "ADEA": "Adeia Inc.", "ADI": "Analog Devices", "ADM": "Archer Daniels Midland",
    "ADMA": "Adma Biologics Inc.", "ADNT": "Adient PLC", "ADP": "Automatic Data Processing",
    "ADPT": "Adaptive Biotechnologies Corp.", "ADRO": "Chinook Therapeutics Inc. Cvr", "ADSK": "Autodesk",
    "ADT": "Adt Inc.", "ADTN": "Adtran Holdings Inc.", "ADUS": "Addus Homecare Corp.",
    "ADV": "Advantage Solutions Inc. Class A", "AEBI": "Aebi Schmidt Holding AG", "AEE": "Ameren",
    "AEHR": "Aehr Test Systems", "AEIS": "Advanced Energy Industries Inc.", "AEO": "American Eagle Outfitters Inc.",
    "AEP": "American Electric Power", "AES": "AES Corporation", "AESI": "Atlas Energy Solutions Inc.",
    "AEVA": "Aeva Technologies Inc.", "AFG": "American Financial Group Inc.", "AFL": "Aflac",
    "AFRM": "Affirm Holdings Inc. Class A", "AGCO": "Agco Corp.", "AGIO": "Agios Pharmaceuticals Inc.",
    "AGL": "Agilon Health", "AGM": "Federal Agricultural Mortgage Non", "AGNC": "Agnc Investment REIT Corp.",
    "AGO": "Assured Guaranty LTD", "AGX": "Argan Inc.", "AGYS": "Agilysys Inc.",
    "AHCO": "Adapthealth Corp.", "AHR": "American Healthcare REIT Inc.", "AHRT": "AH Realty Inc.",
    "AI": "C3 AI Inc. Class A", "AIG": "American International Group", "AIN": "Albany International Corp. Class A",
    "AIOT": "Powerfleet Inc.", "AIP": "Arteris Inc.", "AIR": "Aar Corp.",
    "AIT": "Applied Industrial Technologies IN", "AIZ": "Assurant", "AJG": "Arthur J. Gallagher &amp; Co.",
    "AKAM": "Akamai Technologies", "AKBA": "Akebia Therapeutics Inc.", "AKE": "Akero Therapeutics Cvr",
    "AKR": "Acadia Realty Trust REIT", "AL": "Air Lease Corp. Class A", "ALAB": "Astera Labs Inc.",
    "ALB": "Albemarle Corporation", "ALDX": "Aldeyra Therapeutics Inc.", "ALEC": "Alector Inc.",
    "ALEX": "Alexander and Baldwin Inc.", "ALG": "Alamo Group Inc.", "ALGM": "Allegro Microsystems Inc.",
    "ALGN": "Align Technology", "ALGT": "Allegiant Travel", "ALH": "Alliance Laundry Holdings Inc.",
    "ALHC": "Alignment Healthcare Inc.", "ALIT": "Alight Inc. Class A", "ALK": "Alaska Air Group Inc.",
    "ALKS": "Alkermes", "ALKT": "Alkami Technology Inc.", "ALL": "Allstate",
    "ALLE": "Allegion", "ALLO": "Allogene Therapeutics Inc.", "ALLY": "Ally Financial Inc.",
    "ALMS": "Alumis Inc.", "ALNT": "Allient Inc.", "ALNY": "Alnylam Pharmaceuticals Inc.",
    "ALRM": "Alarm.com Holdings Inc.", "ALRS": "Alerus Financial Corp.", "ALSN": "Allison Transmission Holdings Inc.",
    "ALT": "Altimmune Inc.", "ALTG": "Alta Equipment Group Inc. Class A", "ALX": "Alexanders REIT Inc.",
    "AM": "Antero Midstream Corp.", "AMAL": "Amalgamated Financial Corp.", "AMAT": "Applied Materials",
    "AMBA": "Ambarella Inc.", "AMBP": "Ardagh Metal Packaging SA", "AMC": "Amc Entertainment Holdings Inc. Cla",
    "AMCR": "Amcor", "AMCX": "Amc Networks Class A Inc.", "AMD": "Advanced Micro Devices",
    "AME": "Ametek", "AMG": "Affiliated Managers Group Inc.", "AMGN": "Amgen",
    "AMH": "American Homes Rent REIT Class A", "AMKR": "Amkor Technology Inc.", "AMLX": "Amylyx Pharmaceuticals Inc.",
    "AMN": "Amn Healthcare Inc.", "AMP": "Ameriprise Financial", "AMPH": "Amphastar Pharmaceuticals Inc.",
    "AMPL": "Amplitude Inc. Class A", "AMPX": "Amprius Technologies Inc.", "AMR": "Alpha Metallurgical Resource Inc.",
    "AMRC": "Ameresco Inc. Class A", "AMRX": "Amneal Pharmaceuticals Inc. Class A", "AMSC": "American Superconductor Corp.",
    "AMSF": "Amerisafe Inc.", "AMT": "American Tower", "AMTB": "Amerant Bancorp Inc. Class A",
    "AMTM": "Amentum Holdings Inc.", "AMWD": "American Woodmark Corp.", "AMZN": "Amazon",
    "AN": "Autonation Inc.", "ANAB": "Anaptysbio Inc.", "ANDE": "Andersons Inc.",
    "ANET": "Arista Networks", "ANF": "Abercrombie and Fitch Class A", "ANGI": "Angi Inc. Class A",
    "ANGO": "Angiodynamics Inc.", "ANIK": "Anika Therapeutics Inc.", "ANIP": "Ani Pharmaceuticals Inc.",
    "ANNX": "Annexon Inc.", "AON": "Aon plc", "AORT": "Artivion Inc.",
    "AOS": "A. O. Smith", "AOSL": "Alpha and Omega Semiconductor LTD", "APA": "APA Corporation",
    "APAM": "Artisan Partners Asset Management", "APD": "Air Products", "APEI": "American Public Education Inc.",
    "APG": "APi Group Corp.", "APGE": "Apogee Therapeutics Inc.", "APH": "Amphenol",
    "APLD": "Applied Digital Corp.", "APLE": "Apple Hospitality REIT Inc.", "APLS": "Apellis Pharmaceuticals Inc.",
    "APO": "Apollo Global Management", "APOG": "Apogee Enterprises Inc.", "APP": "AppLovin",
    "APPF": "Appfolio Inc. Class A", "APPN": "Appian Corp. Class A", "APPS": "Digital Turbine Inc.",
    "APTV": "Aptiv", "AQST": "Aquestive Therapeutics Inc.", "AR": "Antero Resources Corp.",
    "ARAY": "Accuray Inc.", "ARCB": "Arcbest Corp.", "ARCT": "Arcturus Therapeutics Holdings Inc.",
    "ARDX": "Ardelyx Inc.", "ARE": "Alexandria Real Estate Equities", "ARES": "Ares Management",
    "ARHS": "Arhaus Inc. Class A", "ARI": "Apollo Commercial Real Estate Fina", "ARLO": "Arlo Technologies Inc.",
    "ARMK": "Aramark", "AROC": "Archrock Inc.", "AROW": "Arrow Financial Corp.",
    "ARQT": "Arcutis Biotherapeutics Inc.", "ARR": "Armour Residential REIT Inc.", "ARRY": "Array Technologies Inc.",
    "ARVN": "Arvinas Inc.", "ARW": "Arrow Electronics Inc.", "ARWR": "Arrowhead Pharmaceuticals Inc.",
    "AS": "Amer Sports Inc.", "ASAN": "Asana Inc. Class A", "ASB": "Associated Bancorp",
    "ASC": "Ardmore Shipping Corp.", "ASGN": "Asgn Inc.", "ASH": "Ashland Inc.",
    "ASIX": "Advansix Inc.", "ASLE": "Aersale Corp.", "ASO": "Academy Sports and Outdoors Inc.",
    "ASPI": "Asp Isotopes Inc.", "ASPN": "Aspen Aerogels Inc.", "ASTE": "Astec Industries Inc.",
    "ASTH": "Astrana Health Inc.", "ASTS": "Ast Spacemobile Inc. Class A", "ASUR": "Asure Software Inc.",
    "ATEC": "Alphatec Holdngs Inc.", "ATEN": "A10 Networks Inc.", "ATEX": "Anterix Inc.",
    "ATI": "Ati Inc.", "ATKR": "Atkore Inc.", "ATMU": "Atmus Filtration Technologies Inc.",
    "ATNI": "Atn International Inc.", "ATO": "Atmos Energy", "ATR": "Aptargroup Inc.",
    "ATRC": "Atricure Inc.", "ATRO": "Astronics Corp.", "ATYR": "Atyr Pharma Inc.",
    "AU": "Anglogold Ashanti PLC", "AUB": "Atlantic Union Bankshares Corp.", "AUPH": "Aurinia Pharmaceuticals Inc.",
    "AUR": "Aurora Innovation Inc. Class A", "AURA": "Aura Biosciences Inc.", "AVA": "Avista Corp.",
    "AVAH": "Aveanna Healthcare Holdings Inc.", "AVAV": "Aerovironment Inc.", "AVB": "AvalonBay Communities",
    "AVBP": "Arrivent Biopharma Inc.", "AVD": "Amer Vanguard Corp.", "AVGO": "Broadcom",
    "AVIR": "Atea Pharmaceuticals Inc.", "AVNS": "Avanos Medical Inc.", "AVNT": "Avient Corp.",
    "AVNW": "Aviat Networks Inc.", "AVO": "Mission Produce Inc.", "AVPT": "Avepoint Inc. Class A",
    "AVT": "Avnet Inc.", "AVTR": "Avantor Inc.", "AVXL": "Anavex Life Sciences Corp.",
    "AVY": "Avery Dennison", "AWI": "Armstrong World Industries Inc.", "AWK": "American Water Works",
    "AWR": "American States Water", "AX": "Axos Financial Inc.", "AXGN": "Axogen Inc.",
    "AXON": "Axon Enterprise", "AXP": "American Express", "AXS": "Axis Capital Holdings LTD",
    "AXSM": "Axsome Therapeutics Inc.", "AXTA": "Axalta Coating Systems LTD", "AYI": "Acuity Inc.",
    "AZO": "AutoZone", "AZTA": "Azenta Inc.", "AZZ": "Azz Inc.",
    "BA": "Boeing", "BAC": "Bank of America", "BAH": "Booz Allen Hamilton Holding Corp. C",
    "BALL": "Ball Corporation", "BAM": "Brookfield Asset Management Voting", "BANC": "Banc of California Inc.",
    "BAND": "Bandwidth Inc. Class A", "BANF": "Bancfirst Corp.", "BANR": "Banner Corp.",
    "BATRA": "Atlanta Braves Holdings Inc. Series", "BATRK": "Atlanta Braves Holdings Inc. Series", "BAX": "Baxter International",
    "BBAI": "Bigbear.ai Holdings Inc.", "BBBY": "Bed Bath and Beyond Inc.", "BBIO": "Bridgebio Pharma Inc.",
    "BBNX": "Beta Bionics Inc.", "BBSI": "Barrett Business Services Inc.", "BBT": "Beacon Financial Corp.",
    "BBUC": "Brookfield Business Corp. Class A", "BBW": "Build A Bear Workshop Inc.", "BBWI": "Bath and Body Works Inc.",
    "BBY": "Best Buy", "BC": "Brunswick Corp.", "BCAL": "California Bancorp",
    "BCAX": "Bicara Therapeutics Inc.", "BCBP": "Bcb Bancorp Inc.", "BCC": "Boise Cascade",
    "BCML": "Baycom Corp.", "BCO": "Brinks", "BCPC": "Balchem Corp.",
    "BCRX": "Biocryst Pharmaceuticals Inc.", "BDC": "Belden Inc.", "BDN": "Brandywine Realty Trust REIT",
    "BDX": "Becton Dickinson", "BE": "Bloom Energy Class A Corp.", "BEAM": "Beam Therapeutics Inc.",
    "BELFB": "Bel Fuse Inc. Class B", "BEN": "Franklin Resources", "BEPC": "Brookfield Renewable Subordinate V",
    "BETR": "Better Home Finance Holding Class", "BF.B": "Brown–Forman", "BFA": "Brown Forman Corp. Class A",
    "BFAM": "Bright Horizons Family Solutions I", "BFB": "Brown Forman Corp. Class B", "BFC": "Bank First Corp.",
    "BFH": "Bread Financial Holdings Inc.", "BFLY": "Butterfly Network Inc. Class A", "BFS": "Saul Centers REIT Inc.",
    "BFST": "Business First Bancshares Inc.", "BG": "Bunge Global", "BGC": "Bgc Group Inc. Class A",
    "BGS": "B and G Foods Inc.", "BHB": "Bar Harbor Bankshares", "BHE": "Benchmark Electronics Inc.",
    "BHF": "Brighthouse Financial Inc.", "BHR": "Braemar Hotels Resorts Inc.", "BHRB": "Burke Herbert Financial Services C",
    "BHVN": "Biohaven LTD", "BIIB": "Biogen", "BILL": "Bill Holdings Inc.",
    "BIO": "Bio Rad Laboratories Inc. Class A", "BIPC": "Brookfield Infrastructure Corp. Cla", "BIRK": "Birkenstock Holding PLC",
    "BJ": "Bjs Wholesale Club Holdings Inc.", "BJRI": "Bjs Restaurants Inc.", "BK": "BNY Mellon",
    "BKD": "Brookdale Senior Living Inc.", "BKE": "Buckle Inc.", "BKH": "Black Hills Corp.",
    "BKNG": "Booking Holdings", "BKR": "Baker Hughes", "BKSY": "Blacksky Technology Inc. Class A",
    "BKU": "Bankunited Inc.", "BKV": "Bkv Corp.", "BL": "Blackline Inc.",
    "BLBD": "Blue Bird Corp.", "BLD": "Topbuild Corp.", "BLDR": "Builders FirstSource",
    "BLFS": "Biolife Solutions Inc.", "BLFY": "Blue Foundry Bancorp", "BLK": "BlackRock",
    "BLKB": "Blackbaud Inc.", "BLMN": "Bloomin Brands Inc.", "BLND": "Blend Labs Inc. Class A",
    "BLSH": "Bullish", "BLX": "Banco Latinoamericano de Comercio", "BMBL": "Bumble Inc. Class A",
    "BMI": "Badger Meter Inc.", "BMRC": "Bank of Marin Bancorp", "BMRN": "Biomarin Pharmaceutical Inc.",
    "BMY": "Bristol Myers Squibb", "BNL": "Broadstone Net Lease Inc.", "BOC": "Boston Omaha Corp. Class A",
    "BOH": "Bank of Hawaii Corp.", "BOKF": "Bok Financial Corp.", "BOOM": "Dmc Global Inc.",
    "BOOT": "Boot Barn Holdings Inc.", "BORR": "Borr Drilling LTD", "BOW": "Bowhead Specialty Holdings Inc.",
    "BOX": "Box Inc. Class A", "BPOP": "Popular Inc.", "BR": "Broadridge Financial Solutions",
    "BRBR": "Bellring Brands Inc.", "BRCC": "Brc Inc. Class A", "BRK.B": "Berkshire Hathaway",
    "BRKB": "Berkshire Hathaway Inc. Class B", "BRKR": "Bruker Corp.", "BRO": "Brown &amp; Brown",
    "BROS": "Dutch Bros Inc. Class A", "BRSL": "Brightstar Lottery PLC", "BRSP": "Brightspire Capital Inc. Class A",
    "BRX": "Brixmor Property Group REIT Inc.", "BRZE": "Braze Inc. Class A", "BSRR": "Sierra Bancorp",
    "BSX": "Boston Scientific", "BSY": "Bentley Systems Inc. Class B", "BTBT": "Bit Digital Inc.",
    "BTDR": "Bitdeer Technologies Group Class A", "BTSG": "Brightspring Health Services Inc.", "BTU": "Peabody Energy Corp.",
    "BULL": "Webull Corp. Class A", "BUR": "Burford Capital LTD", "BURL": "Burlington Stores Inc.",
    "BUSE": "First Busey Corp.", "BV": "Brightview Holdings Inc.", "BVS": "Bioventus Class A Inc.",
    "BWA": "Borgwarner Inc.", "BWB": "Bridgewater Bancshares Inc.", "BWIN": "Baldwin Insurance Group Inc. Class",
    "BWMN": "Bowman Consulting Group LTD", "BWXT": "Bwx Technologies Inc.", "BX": "Blackstone Inc.",
    "BXC": "Bluelinx Holdings Inc.", "BXMT": "Blackstone Mortgage Trust REIT Cla", "BXP": "BXP, Inc.",
    "BY": "Byline Bancorp Inc.", "BYD": "Boyd Gaming Corp.", "BYND": "Beyond Meat Inc.",
    "BYRN": "Byrna Technologies Inc.", "BZH": "Beazer Homes Inc.", "C": "Citigroup",
    "CABO": "Cable One Inc.", "CAC": "Camden National Corp.", "CACC": "Credit Acceptance Corp.",
    "CACI": "Caci International Inc. Class A", "CAG": "Conagra Brands", "CAH": "Cardinal Health",
    "CAI": "Caris Life Sciences Inc.", "CAKE": "Cheesecake Factory Inc.", "CAL": "Caleres Inc.",
    "CALM": "Cal Maine Foods Inc.", "CALX": "Calix Networks Inc.", "CALY": "Callaway Golf Company",
    "CAPR": "Capricor Therapeutics Inc.", "CAR": "Avis Budget Group Inc.", "CARE": "Carter Bankshares Inc.",
    "CARG": "Cargurus Inc. Class A", "CARR": "Carrier Global", "CARS": "Cars.com Inc.",
    "CART": "Maplebear Inc.", "CASH": "Pathward Financial Inc.", "CASS": "Cass Information Systems Inc.",
    "CASY": "Caseys General Stores Inc.", "CAT": "Caterpillar Inc.", "CATX": "Perspective Therapeutics Inc.",
    "CATY": "Cathay General Bancorp", "CAVA": "Cava Group Inc.", "CB": "Chubb Limited",
    "CBAN": "Colony Bankcorp Inc.", "CBL": "Cbl Associates Properties Inc.", "CBLL": "Ceribell Inc.",
    "CBOE": "Cboe Global Markets", "CBRE": "CBRE Group", "CBRL": "Cracker Barrel Old Country Store I",
    "CBSH": "Commerce Bancshares Inc.", "CBT": "Cabot Corp.", "CBU": "Community Financial System Inc.",
    "CBZ": "Cbiz Inc.", "CC": "Chemours", "CCB": "Coastal Financial Corp.",
    "CCBG": "Capital City Bank Inc.", "CCC": "Ccc Intelligent Solutions Holdings", "CCI": "Crown Castle",
    "CCK": "Crown Holdings Inc.", "CCL": "Carnival", "CCNE": "Cnb Financial Corp.",
    "CCOI": "Cogent Communications Holdings Inc.", "CCRN": "Cross Country Healthcare Inc.", "CCS": "Century Communities Inc.",
    "CCSI": "Consensus Cloud Solutions Inc.", "CDE": "Coeur Mining Inc.", "CDNA": "Caredx Inc.",
    "CDNS": "Cadence Design Systems", "CDP": "Copt Defense Properties", "CDRE": "Cadre Holdings Inc.",
    "CDW": "CDW Corporation", "CDXS": "Codexis Inc.", "CE": "Celanese Corp.",
    "CECO": "Ceco Environmental Corp.", "CEG": "Constellation Energy", "CELC": "Celcuity Inc.",
    "CELH": "Celsius Holdings Inc.", "CENT": "Central Garden and Pet", "CENTA": "Central Garden and Pet Class A",
    "CENX": "Century Aluminum", "CERS": "Cerus Corp.", "CERT": "Certara Inc.",
    "CEVA": "Ceva Inc.", "CF": "CF Industries", "CFFN": "Capitol Federal Financial Inc.",
    "CFG": "Citizens Financial Group", "CFLT": "Confluent Inc. Class A", "CFR": "Cullen Frost Bankers Inc.",
    "CG": "Carlyle Group Inc.", "CGEM": "Cullinan Therapeutics Inc.", "CGNX": "Cognex Corp.",
    "CGON": "CG Oncology Inc.", "CHCO": "City Holding", "CHCT": "Community Healthcare Trust Inc.",
    "CHD": "Church &amp; Dwight", "CHDN": "Churchill Downs Inc.", "CHE": "Chemed Corp.",
    "CHEF": "Chefs Warehouse Inc.", "CHH": "Choice Hotels International Inc.", "CHRD": "Chord Energy Corp.",
    "CHRS": "Coherus Oncology Inc.", "CHRW": "C.H. Robinson", "CHTR": "Charter Communications",
    "CHWY": "Chewy Inc. Class A", "CI": "Cigna", "CIEN": "Ciena",
    "CIFR": "Cipher Digital Inc.", "CIM": "Chimera Investment Corp.", "CINF": "Cincinnati Financial",
    "CIVB": "Civista Bancshares Inc.", "CL": "Colgate-Palmolive", "CLB": "Core Laboratories Inc.",
    "CLBK": "Columbia Financial Inc.", "CLDT": "Chatham Lodging Trust REIT", "CLDX": "Celldex Therapeutics Inc.",
    "CLF": "Cleveland Cliffs Inc.", "CLFD": "Clearfield Inc.", "CLH": "Clean Harbors Inc.",
    "CLMB": "Climb Global Solutions Inc.", "CLMT": "Calumet Inc.", "CLNE": "Clean Energy Fuels Corp.",
    "CLOV": "Clover Health Investments Corp. Cla", "CLPT": "Clearpoint Neuro Inc.", "CLSK": "Cleanspark Inc.",
    "CLVT": "Clarivate PLC", "CLW": "Clearwater Paper Corp.", "CLX": "Clorox",
    "CMC": "Commercial Metals", "CMCL": "Caledonia Mining PLC", "CMCO": "Columbus Mckinnon Corp.",
    "CMCSA": "Comcast", "CMDB": "Costamare Bulkers Holdings LTD", "CME": "CME Group",
    "CMG": "Chipotle Mexican Grill", "CMI": "Cummins", "CMP": "Compass Minerals International Inc.",
    "CMPR": "Cimpress PLC", "CMPX": "Compass Therapeutics", "CMRC": "Bigcommerce Holdings Inc. Series",
    "CMRE": "Costamare Inc.", "CMS": "CMS Energy", "CMT": "Core Molding Technologies Inc.",
    "CMTG": "Claros Mortgage Trust Inc.", "CNA": "Cna Financial Corp.", "CNC": "Centene Corporation",
    "CNDT": "Conduent Inc.", "CNH": "Cnh Industrial N.v NV", "CNK": "Cinemark Holdings Inc.",
    "CNM": "Core & Main Inc. Class A", "CNMD": "Conmed Corp.", "CNNE": "Cannae Holdings Inc.",
    "CNO": "Cno Financial Group Inc.", "CNOB": "Connectone Bancorp Inc.", "CNP": "CenterPoint Energy",
    "CNR": "Core Natural Resources Inc.", "CNS": "Cohen & Steers Inc.", "CNX": "Cnx Resources Corp.",
    "CNXC": "Concentrix Corp.", "CNXN": "PC Connection Inc.", "COCO": "The Vita Coco Company Inc.",
    "CODI": "Compass Diversified", "COF": "Capital One", "COFS": "Choiceone Financial Services Inc.",
    "COGT": "Cogent Biosciences Inc.", "COHR": "Coherent Corp.", "COHU": "Cohu Inc.",
    "COIN": "Coinbase", "COKE": "Coca Cola Consolidated Inc.", "COLB": "Columbia Banking System Inc.",
    "COLD": "Americold Realty Inc. Trust", "COLL": "Collegium Pharmaceutical Inc.", "COLM": "Columbia Sportswear",
    "COMP": "Compass Inc. Class A", "CON": "Concentra Group Holdings Parent IN", "COO": "Cooper Companies (The)",
    "COP": "ConocoPhillips", "COR": "Cencora", "CORT": "Corcept Therapeutics Inc.",
    "CORZ": "Core Scientific Inc.", "COST": "Costco", "COTY": "Coty Inc. Class A",
    "COUR": "Coursera Inc.", "CPAY": "Corpay", "CPB": "Campbell's Company (The)",
    "CPF": "Central Pacific Financial Corp.", "CPK": "Chesapeake Utilities Corp.", "CPNG": "Coupang Inc. Class A",
    "CPRI": "Capri Holdings LTD", "CPRT": "Copart", "CPRX": "Catalyst Pharmaceuticals Inc.",
    "CPS": "Cooper Standard Holdings Inc.", "CPT": "Camden Property Trust", "CR": "Crane",
    "CRAI": "Cra International Inc.", "CRC": "California Resources Corp.", "CRCL": "Circle Internet Group Inc. Class A",
    "CRCT": "Cricut Inc. Class A", "CRDO": "Credo Technology Group Holding LTD", "CRGY": "Crescent Energy Class A",
    "CRH": "CRH plc", "CRI": "Carters Inc.", "CRK": "Comstock Resources Inc.",
    "CRL": "Charles River Laboratories", "CRM": "Salesforce", "CRMD": "Cormedix Inc.",
    "CRMT": "Americas Car Mart Inc.", "CRNC": "Cerence Inc.", "CRNX": "Crinetics Pharmaceuticals Inc.",
    "CROX": "Crocs Inc.", "CRS": "Carpenter Technology Corp.", "CRSP": "Crispr Therapeutics AG",
    "CRSR": "Corsair Gaming Inc.", "CRUS": "Cirrus Logic Inc.", "CRVL": "Corvel Corp.",
    "CRVS": "Corvus Pharmaceuticals Inc.", "CRWD": "CrowdStrike", "CSCO": "Cisco",
    "CSGP": "CoStar Group", "CSGS": "Csg Systems International Inc.", "CSL": "Carlisle Companies Inc.",
    "CSR": "Centerspace", "CSTL": "Castle Biosciences Inc.", "CSTM": "Constellium SE Class A",
    "CSV": "Carriage Services Inc.", "CSW": "Csw Industrials Inc.", "CSX": "CSX Corporation",
    "CTAS": "Cintas", "CTBI": "Community Trust Bancorp Inc.", "CTKB": "Cytek Biosciences Inc.",
    "CTLP": "Cantaloupe Inc.", "CTO": "Cto Realty Growth Inc.", "CTOS": "Custom Truck One Source Inc.",
    "CTRA": "Coterra", "CTRE": "Caretrust REIT Inc.", "CTRI": "Centuri Holdings Inc.",
    "CTS": "Cts Corp.", "CTSH": "Cognizant", "CTVA": "Corteva",
    "CUBE": "Cubesmart REIT", "CUBI": "Customers Bancorp Inc.", "CURB": "Curbline Properties",
    "CUZ": "Cousins Properties REIT Inc.", "CVBF": "Cvb Financial Corp.", "CVCO": "Cavco Industries Inc.",
    "CVGW": "Calavo Growers Inc.", "CVI": "Cvr Energy Inc.", "CVLG": "Covenant Logistics Group Inc. Class",
    "CVLT": "Commvault Systems Inc.", "CVNA": "Carvana", "CVRX": "Cvrx Inc.",
    "CVS": "CVS Health", "CVSA": "Covista Inc.", "CVX": "Chevron Corporation",
    "CW": "Curtiss Wright Corp.", "CWAN": "Clearwater Analytics Holdings Inc.", "CWBC": "Community West Bancshares",
    "CWCO": "Consolidated Water LTD", "CWEN": "Clearway Energy Inc. Class C", "CWENA": "Clearway Energy Inc. Class A",
    "CWH": "Camping World Holdings Inc. Class A", "CWK": "Cushman and Wakefield LTD", "CWST": "Casella Waste Systems Inc. Class A",
    "CWT": "California Water Service Group", "CXM": "Sprinklr Inc. Class A", "CXT": "Crane Nxt",
    "CXW": "Corecivic REIT Inc.", "CYH": "Community Health Systems Inc.", "CYRX": "Cryoport Inc.",
    "CYTK": "Cytokinetics Inc.", "CZFS": "Citizens Financial Services Inc.", "CZNC": "Citizens and Northern Corp.",
    "CZR": "Caesars Entertainment Inc.", "D": "Dominion Energy", "DAKT": "Daktronics Inc.",
    "DAL": "Delta Air Lines", "DAN": "Dana Incorporated Inc.", "DAR": "Darling Ingredients Inc.",
    "DASH": "DoorDash", "DAVE": "Dave Inc. Class A", "DAWN": "Day One Biopharmaceuticals Inc.",
    "DBD": "Diebold Nixdorf Inc.", "DBI": "Designer Brands Inc. Class A", "DBRG": "Digitalbridge Group Inc. Class A",
    "DBX": "Dropbox Inc. Class A", "DC": "Dakota Gold Corp.", "DCGO": "Docgo Inc.",
    "DCH": "Dauch Corporation", "DCI": "Donaldson Inc.", "DCO": "Ducommun Inc.",
    "DCOM": "Dime Community Bancshares Inc.", "DD": "DuPont", "DDD": "3d Systems Corp.",
    "DDOG": "Datadog", "DDS": "Dillards Inc. Class A", "DE": "Deere &amp; Company",
    "DEA": "Easterly Government Properties Inc.", "DEC": "Diversified Energy Company", "DECK": "Deckers Brands",
    "DEI": "Douglas Emmett REIT Inc.", "DELL": "Dell Technologies", "DFH": "Dream Finders Homes Inc. Class A",
    "DFIN": "Donnelley Financial Solutions Inc.", "DFTX": "Definium Therapeutics Inc.", "DG": "Dollar General",
    "DGICA": "Donegal Group Inc. Class A", "DGII": "Digi International Inc.", "DGX": "Quest Diagnostics",
    "DH": "Definitive Healthcare Corp. Class A", "DHC": "Diversified Healthcare Trust", "DHI": "D. R. Horton",
    "DHIL": "Diamond Hill Investment Group Inc.", "DHR": "Danaher Corporation", "DHT": "Dht Holdings Inc.",
    "DIN": "Dine Brands Global Inc.", "DINO": "HF Sinclair Corp.", "DIOD": "Diodes Inc.",
    "DIS": "Walt Disney Company (The)", "DJCO": "Daily Journal Corp.", "DJT": "Trump Media Technology Group Corp.",
    "DK": "Delek US Holdings Inc.", "DKNG": "Draftkings Inc. Class A", "DKS": "Dicks Sporting Inc.",
    "DLB": "Dolby Laboratories Inc. Class A", "DLR": "Digital Realty", "DLTR": "Dollar Tree",
    "DLX": "Deluxe Corp.", "DMRC": "Digimarc Corp.", "DNLI": "Denali Therapeutics Inc.",
    "DNOW": "Dnow Inc.", "DNTH": "Dianthus Therapeutics Inc.", "DNUT": "Krispy Kreme Inc.",
    "DOC": "Healthpeak Properties", "DOCN": "Digitalocean Holdings Inc.", "DOCS": "Doximity Inc. Class A",
    "DOCU": "Docusign Inc.", "DOLE": "Dole PLC", "DOMO": "Domo Inc. Class B",
    "DORM": "Dorman Products Inc.", "DOV": "Dover Corporation", "DOW": "Dow Inc.",
    "DOX": "Amdocs LTD", "DPZ": "Domino's", "DRH": "Diamondrock Hospitality",
    "DRI": "Darden Restaurants", "DRS": "Leonardo Drs Inc.", "DRUG": "Bright Minds Biosciences Inc.",
    "DRVN": "Driven Brands Holdings Inc.", "DSGN": "Design Therapeutics Inc.", "DSGR": "Distribution Solutions Group Inc.",
    "DSP": "Viant Technology Inc. Class A", "DT": "Dynatrace Inc.", "DTE": "DTE Energy",
    "DTM": "DT Midstream Inc.", "DUK": "Duke Energy", "DUOL": "Duolingo Inc. Class A",
    "DV": "Doubleverify Holdings Inc.", "DVA": "DaVita", "DVN": "Devon Energy",
    "DX": "Dynex Capital REIT Inc.", "DXC": "Dxc Technology", "DXCM": "Dexcom",
    "DXPE": "Dxp Enterprises Inc.", "DY": "Dycom Industries Inc.", "DYN": "Dyne Therapeutics Inc.",
    "EA": "Electronic Arts", "EAT": "Brinker International Inc.", "EB": "Eventbrite Class A Inc.",
    "EBAY": "eBay Inc.", "EBC": "Eastern Bankshares Inc.", "EBF": "Ennis Inc.",
    "EBS": "Emergent Biosolutions Inc.", "ECG": "Everus Construction Group Inc.", "ECL": "Ecolab",
    "ECPG": "Encore Capital Group Inc.", "ECVT": "Ecovyst Inc.", "ED": "Consolidated Edison",
    "EDIT": "Editas Medicine Inc.", "EE": "Excelerate Energy Inc. Class A", "EEFT": "Euronet Worldwide Inc.",
    "EFC": "Ellington Financial Inc.", "EFSC": "Enterprise Financial Services Corp.", "EFX": "Equifax",
    "EG": "Everest Group", "EGBN": "Eagle Bancorp Inc.", "EGHT": "8x8 Inc.",
    "EGP": "Eastgroup Properties REIT Inc.", "EGY": "Vaalco Energy Inc.", "EHAB": "Enhabit Inc.",
    "EHC": "Encompass Health Corp.", "EIG": "Employers Holdings Inc.", "EIX": "Edison International",
    "EL": "Estée Lauder Companies (The)", "ELAN": "Elanco Animal Health Inc.", "ELF": "Elf Beauty Inc.",
    "ELS": "Equity Lifestyle Properties REIT I", "ELV": "Elevance Health", "ELVN": "Enliven Therapeutics Inc.",
    "EMBC": "Embecta Corp.", "EME": "EMCOR Group Inc.", "EMN": "Eastman Chemical",
    "EMR": "Emerson Electric", "ENOV": "Enovis Corp.", "ENPH": "Enphase Energy Inc.",
    "ENR": "Energizer Holdings Inc.", "ENS": "Enersys", "ENSG": "Ensign Group Inc.",
    "ENTA": "Enanta Pharmaceuticals Inc.", "ENTG": "Entegris Inc.", "ENVA": "Enova International Inc.",
    "ENVX": "Enovix Corp.", "EOG": "EOG Resources", "EOLS": "Evolus Inc.",
    "EOSE": "Eos Energy Enterprises Inc. Class A", "EPAC": "Enerpac Tool Group Corp. Class A", "EPAM": "EPAM Systems",
    "EPC": "Edgewell Personal Care", "EPM": "Evolution Petroleum Corp.", "EPR": "Epr Properties REIT",
    "EPRT": "Essential Properties Realty Trust", "EQBK": "Equity Bancshares Inc. Class A", "EQH": "Equitable Holdings Inc.",
    "EQIX": "Equinix", "EQR": "Equity Residential", "EQT": "EQT Corporation",
    "ERAS": "Erasca Inc.", "ERIE": "Erie Indemnity", "ERII": "Energy Recovery Inc.",
    "ES": "Eversource Energy", "ESAB": "Esab Corp.", "ESE": "Esco Technologies Inc.",
    "ESI": "Element Solutions Inc.", "ESNT": "Essent Group LTD", "ESPR": "Esperion Therapeutics Inc.",
    "ESQ": "Esquire Financial Holdings Inc.", "ESRT": "Empire State Realty REIT Inc. Trust", "ESS": "Essex Property Trust",
    "ESTC": "Elastic NV", "ETD": "Ethan Allen Interiors Inc.", "ETN": "Eaton Corporation",
    "ETR": "Entergy", "ETSY": "Etsy Inc.", "EU": "Encore Energy Corp.",
    "EVC": "Entravision Communications Corp. CL", "EVCM": "Evercommerce Inc.", "EVER": "Everquote Inc. Class A",
    "EVGO": "Evgo Inc. Class A", "EVH": "Evolent Health Inc. Class A", "EVLV": "Evolv Technologies Holdings Inc. CL",
    "EVR": "Evercore Inc. Class A", "EVRG": "Evergy", "EVTC": "Evertec Inc.",
    "EW": "Edwards Lifesciences", "EWBC": "East West Bancorp Inc.", "EWCZ": "European Wax Center Inc. Class A",
    "EWTX": "Edgewise Therapeutics Inc.", "EXAS": "Exact Sciences Corp.", "EXC": "Exelon",
    "EXE": "Expand Energy", "EXEL": "Exelixis Inc.", "EXLS": "Exlservice Holdings Inc.",
    "EXP": "Eagle Materials Inc.", "EXPD": "Expeditors International", "EXPE": "Expedia Group",
    "EXPI": "Exp World Holdings Inc.", "EXPO": "Exponent Inc.", "EXR": "Extra Space Storage",
    "EXTR": "Extreme Networks Inc.", "EYE": "National Vision Holdings Inc.", "EYPT": "Eyepoint Inc.",
    "F": "Ford Motor Company", "FA": "First Advantage Corp.", "FAF": "First American Financial Corp.",
    "FANG": "Diamondback Energy", "FAST": "Fastenal", "FATE": "Fate Therapeutics Inc.",
    "FBIN": "Fortune Brands Innovations Inc.", "FBIZ": "First Business Financial Services", "FBK": "FB Financial Corp.",
    "FBNC": "First Bancorp", "FBP": "First Bancorp", "FBRT": "Franklin Bsp Realty Trust Inc.",
    "FC": "Franklin Covey", "FCBC": "First Community Bankshares Inc.", "FCF": "First Commonwealth Financial Corp.",
    "FCFS": "Firstcash Holdings Inc.", "FCN": "Fti Consulting Inc.", "FCNCA": "First Citizens Bancshares Inc. Clas",
    "FCPT": "Four Corners Property Inc. Trust", "FCX": "Freeport-McMoRan", "FDBC": "Fidelity D and D Bancorp Inc.",
    "FDMT": "4d Molecular Therapeutics Inc.", "FDP": "Fresh del Monte Produce Inc.", "FDS": "FactSet",
    "FDX": "FedEx", "FE": "FirstEnergy", "FELE": "Franklin Electric Inc.",
    "FERG": "Ferguson Enterprises Inc.", "FFBC": "First Financial Bancorp", "FFIC": "Flushing Financial Corp.",
    "FFIN": "First Financial Bankshares Inc.", "FFIV": "F5, Inc.", "FFWM": "First Foundation Inc.",
    "FG": "F&g Annuities and Life Inc.", "FHB": "First Hawaiian Inc.", "FHN": "First Horizon Corp.",
    "FIBK": "First Interstate Bancsystem Inc.", "FICO": "Fair Isaac", "FIGR": "Figure Technology Solutions Inc. CL",
    "FIGS": "Figs Inc. Class A", "FIHL": "Fidelis Insurance Holdings LTD", "FIP": "Ftai Infrastructure Inc.",
    "FIS": "Fidelity National Information Services", "FISI": "Financial Institutions Inc.", "FISV": "Fiserv",
    "FITB": "Fifth Third Bancorp", "FIVE": "Five Below Inc.", "FIVN": "Five9 Inc.",
    "FIX": "Comfort Systems USA", "FIZZ": "National Beverage Corp.", "FLEX": "Flex LTD",
    "FLG": "Flagstar Bank National Association", "FLGT": "Fulgent Genetics Inc.", "FLNC": "Fluence Energy Inc. Class A",
    "FLNG": "Flex Lng LTD", "FLO": "Flowers Foods Inc.", "FLR": "Fluor Corp.",
    "FLS": "Flowserve Corp.", "FLUT": "Flutter Entertainment PLC", "FLWS": "1-800 Flowers.com Inc. Class A",
    "FLY": "Firefly Aerospace Inc.", "FLYW": "Flywire Corp.", "FMAO": "Farmers and Merchants Bancorp Inc.",
    "FMBH": "First Mid Bancshares Inc.", "FMC": "Fmc Corp.", "FMNB": "Farmers National Banc Corp.",
    "FN": "Fabrinet", "FNB": "Fnb Corp.", "FND": "Floor Decor Holdings Inc. Class A",
    "FNF": "Fidelity National Financial Inc.", "FNKO": "Funko Inc. Class A", "FNLC": "First Bancorp Inc.",
    "FOLD": "Amicus Therapeutics Inc.", "FOR": "Forestar Group Inc.", "FORM": "Formfactor Inc.",
    "FORR": "Forrester Research Inc.", "FOUR": "Shift4 Payments Inc. Class A", "FOX": "Fox Corporation (Class B)",
    "FOXA": "Fox Corporation (Class A)", "FOXF": "Fox Factory Holding Corp.", "FPI": "Farmland Partners Inc.",
    "FR": "First Industrial Realty Trust Inc.", "FRBA": "First Bank", "FRHC": "Freedom Holding Corp.",
    "FRME": "First Merchants Corp.", "FRPH": "Frp Holdings Inc.", "FRPT": "Freshpet Inc.",
    "FRSH": "Freshworks Inc. Class A", "FRST": "Primis Financial Corp.", "FRT": "Federal Realty Investment Trust",
    "FSBC": "Five Star Bancorp", "FSBW": "FS Bancorp Inc.", "FSLR": "First Solar",
    "FSLY": "Fastly Inc. Class A", "FSS": "Federal Signal Corp.", "FSUN": "Firstsun Capital Bancorp",
    "FTAI": "FTAI Aviation", "FTDR": "Frontdoor Inc.", "FTI": "Technipfmc PLC",
    "FTNT": "Fortinet", "FTRE": "Fortrea Holdings Inc.", "FTV": "Fortive",
    "FUBO": "Fubotv Inc. Class A", "FUL": "HB Fuller", "FULC": "Fulcrum Therapeutics Inc.",
    "FULT": "Fulton Financial Corp.", "FUN": "Six Flags Entertainment Corp.", "FWONA": "Liberty Media Formula One Series A",
    "FWONK": "Liberty Media Formula One Series C", "FWRD": "Forward Air Corp.", "FWRG": "First Watch Restaurant Group Inc.",
    "G": "Genpact LTD", "GABC": "German American Bancorp Inc.", "GAP": "Gap Inc.",
    "GATX": "Gatx Corp.", "GBCI": "Glacier Bancorp Inc.", "GBTG": "Global Business Travel Group Inc. C",
    "GBX": "Greenbrier Inc.", "GCMG": "Gcm Grosvenor Inc. Class A", "GCO": "Genesco Inc.",
    "GCT": "Gigacloud Technology Inc. Class A", "GD": "General Dynamics", "GDDY": "GoDaddy",
    "GDEN": "Golden Entertainment Inc.", "GDOT": "Green Dot Corp. Class A", "GDYN": "Grid Dynamics Holdings Inc. Class A",
    "GE": "GE Aerospace", "GEF": "Greif Inc. Class A", "GEFB": "Greif Inc. Class B",
    "GEHC": "GE HealthCare", "GEN": "Gen Digital", "GENI": "Genius Sports LTD",
    "GEO": "Geo Group Inc.", "GERN": "Geron Corp.", "GETY": "Getty Images Holdings Inc. Class A",
    "GEV": "GE Vernova", "GFF": "Griffon Corp.", "GFS": "Globalfoundries Inc.",
    "GGG": "Graco Inc.", "GH": "Guardant Health Inc.", "GHC": "Graham Holdings Company Class B",
    "GHM": "Graham Corp.", "GIC": "Global Industrial", "GIII": "G III Apparel Group LTD",
    "GILD": "Gilead Sciences", "GIS": "General Mills", "GKOS": "Glaukos Corp.",
    "GL": "Globe Life", "GLDD": "Great Lakes Dredge and Dock Corp.", "GLIBA": "Gci Liberty Inc. Series A",
    "GLIBK": "Gci Liberty Inc. Series C", "GLNG": "Golar Lng LTD", "GLOB": "Globant SA",
    "GLPI": "Gaming and Leisure Properties REIT", "GLRE": "Greenlight Capital LTD Class A", "GLUE": "Monte Rosa Therapeutics Inc.",
    "GLW": "Corning Inc.", "GM": "General Motors", "GME": "Gamestop Corp. Class A",
    "GMED": "Globus Medical Inc. Class A", "GNE": "Genie Energy LTD Class B", "GNK": "Genco Shipping and Trading LTD",
    "GNL": "Global Net Lease Inc.", "GNRC": "Generac", "GNTX": "Gentex Corp.",
    "GNW": "Genworth Financial Inc.", "GO": "Grocery Outlet Holding Corp.", "GOGO": "Gogo Inc.",
    "GOLD": "Gold Inc.", "GOLF": "Acushnet Holdings Corp.", "GOOD": "Gladstone Commercial REIT Corp.",
    "GOOG": "Alphabet Inc. (Class C)", "GOOGL": "Alphabet Inc. (Class A)", "GOSS": "Gossamer Bio Inc.",
    "GPC": "Genuine Parts Company", "GPGI": "Gpgi Inc. Class A", "GPI": "Group Automotive Inc.",
    "GPK": "Graphic Packaging Holding", "GPN": "Global Payments", "GPOR": "Gulfport Energy Corp.",
    "GPRE": "Green Plains Inc.", "GRAL": "Grail Inc.", "GRBK": "Green Brick Partners Inc.",
    "GRC": "Gorman-rupp", "GRDN": "Guardian Pharmacy Services Inc. Cla", "GRMN": "Garmin",
    "GRND": "Grindr Inc.", "GRNT": "Granite Ridge Resources Inc.", "GRPN": "Groupon Inc.",
    "GS": "Goldman Sachs", "GSAT": "Globalstar Voting Inc.", "GSBC": "Great Southern Bancorp Inc.",
    "GSHD": "Goosehead Insurance Inc. Class A", "GT": "Goodyear Tire & Rubber", "GTES": "Gates Industrial PLC",
    "GTLB": "Gitlab Inc. Class A", "GTLS": "Chart Industries Inc.", "GTM": "Zoominfo Technologies Inc.",
    "GTN": "Gray Media Inc.", "GTX": "Garrett Motion Inc.", "GTXI": "Gtxi Inc. - Cvr",
    "GTY": "Getty Realty REIT Corp.", "GVA": "Granite Construction Inc.", "GWRE": "Guidewire Software Inc.",
    "GWW": "W. W. Grainger", "GXO": "Gxo Logistics Inc.", "H": "Hyatt Hotels Corp. Class A",
    "HAE": "Haemonetics Corp.", "HAFC": "Hanmi Financial Corp.", "HAIN": "Hain Celestial Group Inc.",
    "HAL": "Halliburton", "HALO": "Halozyme Therapeutics Inc.", "HAS": "Hasbro",
    "HASI": "HA Sustainable Infrastructure Capi", "HAYW": "Hayward Holdings Inc.", "HBAN": "Huntington Bancshares",
    "HBCP": "Home Bancorp Inc.", "HBNC": "Horizon Bancorp Inc.", "HBT": "Hbt Financial Inc.",
    "HCA": "HCA Healthcare", "HCAT": "Health Catalyst Inc.", "HCC": "Warrior Met Coal Inc.",
    "HCI": "Hci Group Inc.", "HCKT": "Hackett Group Inc.", "HCSG": "Healthcare Services Group Inc.",
    "HD": "Home Depot (The)", "HDSN": "Hudson Technologies Inc.", "HE": "Hawaiian Electric Industries Inc.",
    "HEI": "Heico Corp.", "HEIA": "Heico Corp. Class A", "HELE": "Helen of Troy LTD",
    "HFWA": "Heritage Financial Corp.", "HG": "Hamilton Insurance Group LTD Class", "HGV": "Hilton Grand Vacations Inc.",
    "HHH": "Howard Hughes Holdings Inc.", "HIFS": "Hingham Institution For Savings", "HIG": "Hartford (The)",
    "HII": "Huntington Ingalls Industries", "HIMS": "Hims Hers Health Inc. Class A", "HIPO": "Hippo Holdings Inc.",
    "HIW": "Highwoods Properties REIT Inc.", "HL": "Hecla Mining", "HLF": "Herbalife LTD",
    "HLI": "Houlihan Lokey Inc. Class A", "HLIO": "Helios Technologies Inc.", "HLIT": "Harmonic Inc.",
    "HLMN": "Hillman Solutions Corp.", "HLNE": "Hamilton Lane Inc. Class A", "HLT": "Hilton Worldwide",
    "HLX": "Helix Energy Solutions Group Inc.", "HMN": "Horace Mann Educators Corp.", "HNI": "Hni Corp.",
    "HNRG": "Hallador Energy", "HNST": "The Honest Company Inc.", "HOG": "Harley Davidson Inc.",
    "HOLX": "Hologic", "HOMB": "Home Bancshares Inc.", "HON": "Honeywell",
    "HOOD": "Robinhood Markets", "HOPE": "Hope Bancorp Inc.", "HOV": "Hovnanian Enterprises Inc. Class A",
    "HP": "Helmerich & Payne Inc.", "HPE": "Hewlett Packard Enterprise", "HPP": "Hudson Pacific Properties REIT Inc.",
    "HPQ": "HP Inc.", "HQY": "Healthequity Inc.", "HR": "Healthcare Realty Trust Inc. Class",
    "HRB": "H&r Block Inc.", "HRI": "Herc Holdings Inc.", "HRL": "Hormel Foods",
    "HRMY": "Harmony Biosciences Hldg Inc.", "HROW": "Harrow Inc.", "HRTG": "Heritage Insurance Holdings Inc.",
    "HRTX": "Heron Therapeutics Inc.", "HSIC": "Henry Schein", "HST": "Host Hotels &amp; Resorts",
    "HSTM": "Healthstream Inc.", "HSY": "Hershey Company (The)", "HTB": "Hometrust Bancshares Inc.",
    "HTBK": "Heritage Commerce Corp.", "HTFL": "Heartflow Inc.", "HTH": "Hilltop Holdings Inc.",
    "HTLD": "Heartland Express Inc.", "HTO": "H2o America", "HTZ": "Hertz Global Hldgs Inc.",
    "HUBB": "Hubbell Incorporated", "HUBG": "Hub Group Inc. Class A", "HUBS": "Hubspot Inc.",
    "HUM": "Humana", "HUMA": "Humacyte Inc.", "HUN": "Huntsman Corp.",
    "HURN": "Huron Consulting Group Inc.", "HUT": "Hut Corp.", "HVT": "Haverty Furniture Companies Inc.",
    "HWC": "Hancock Whitney Corp.", "HWKN": "Hawkins Inc.", "HWM": "Howmet Aerospace",
    "HXL": "Hexcel Corp.", "HY": "Hyster Yale Inc. Class A", "HYLN": "Hyliion Holdings Corp.",
    "HZO": "Marinemax Inc.", "IAC": "Iac Inc.", "IART": "Integra Lifesciences Holdings Corp.",
    "IBCP": "Independent Bank Corp.", "IBKR": "Interactive Brokers", "IBOC": "International Bancshares Corp.",
    "IBP": "Installed Building Products Inc.", "IBRX": "Immunitybio Inc.", "IBTA": "Ibotta Inc. Class A",
    "ICE": "Intercontinental Exchange", "ICFI": "Icf International Inc.", "ICHR": "Ichor Holdings LTD",
    "ICUI": "Icu Medical Inc.", "IDA": "Idacorp Inc.", "IDCC": "Interdigital Inc.",
    "IDR": "Idaho Strategic Resources Inc.", "IDT": "Idt Corp. Class B", "IDXX": "Idexx Laboratories",
    "IDYA": "Ideaya Biosciences Inc.", "IE": "Ivanhoe Electric Inc.", "IESC": "Ies Inc.",
    "IEX": "IDEX Corporation", "IFF": "International Flavors &amp; Fragrances", "IHRT": "Iheartmedia Inc. Class A",
    "IIIN": "Insteel Industries Inc.", "IIIV": "I3 Verticals Inc. Class A", "IIPR": "Innovative Industrial Properties I",
    "ILMN": "Illumina Inc.", "ILPT": "Industrial Logistics Properties TR", "IMAX": "Imax Corp.",
    "IMKTA": "Ingles Markets Inc. Class A", "IMMR": "Immersion Corp.", "IMNM": "Immunome Inc.",
    "IMVT": "Immunovant Inc.", "IMXI": "International Money Express Inc.", "INBK": "First Internet Bancorp",
    "INBX": "Inhibrx Biosciences Inc.", "INCY": "Incyte", "INDB": "Independent Bank Corp.",
    "INDI": "Indie Semiconductor Inc. Class A", "INDV": "Indivior Pharmaceuticals Inc.", "INGM": "Ingram Micro Holding Corp.",
    "INGN": "Inogen Inc.", "INGR": "Ingredion Inc.", "INH": "Inhibrx Inc. Cvr",
    "INN": "Summit Hotel Properties REIT Inc.", "INOD": "Innodata Inc.", "INR": "Infinity Natural Resources Inc. Cla",
    "INSE": "Inspired Entertainment Inc.", "INSM": "Insmed Inc.", "INSP": "Inspire Medical Systems Inc.",
    "INSW": "International Seaways Inc.", "INTA": "Intapp Inc.", "INTC": "Intel",
    "INTU": "Intuit", "INVA": "Innoviva Inc.", "INVH": "Invitation Homes",
    "INVX": "Innovex International Inc.", "IONQ": "Ionq Inc.", "IONS": "Ionis Pharmaceuticals Inc.",
    "IOSP": "Innospec Inc.", "IOT": "Samsara Inc. Class A", "IOVA": "Iovance Biotherapeutics Inc.",
    "IP": "International Paper", "IPAR": "Interparfums Inc.", "IPGP": "Ipg Photonics Corp.",
    "IPI": "Intrepid Potash Inc.", "IQV": "IQVIA", "IR": "Ingersoll Rand",
    "IRDM": "Iridium Communications Inc.", "IRM": "Iron Mountain", "IRMD": "Iradimed Corp.",
    "IRON": "Disc Medicine Inc.", "IRT": "Independence Realty Inc. Trust", "IRTC": "Irhythm Holdings Inc.",
    "IRWD": "Ironwood Pharma Inc. Class A", "ISRG": "Intuitive Surgical", "IT": "Gartner",
    "ITGR": "Integer Holdings Corp.", "ITIC": "Investors Title", "ITRI": "Itron Inc.",
    "ITT": "Itt Inc.", "ITW": "Illinois Tool Works", "IVR": "Invesco Mortgage Capital REIT Inc.",
    "IVT": "Inventrust Properties Corp.", "IVZ": "Invesco", "J": "Jacobs Solutions",
    "JACK": "Jack IN the Box Inc.", "JAKK": "Jakks Pacific Inc.", "JANX": "Janux Therapeutics Inc.",
    "JAZZ": "Jazz Pharmaceuticals PLC", "JBGS": "Jbg Smith Properties", "JBHT": "J.B. Hunt",
    "JBI": "Janus International Group Inc.", "JBIO": "Jade Biosciences Inc.", "JBL": "Jabil",
    "JBLU": "Jetblue Airways Corp.", "JBSS": "John B Sanfilippo and Son Inc.", "JBTM": "Jbt Marel Corp.",
    "JCI": "Johnson Controls", "JEF": "Jefferies Financial Group Inc.", "JELD": "Jeld Wen Holding Inc.",
    "JHG": "Janus Henderson Group PLC", "JHX": "James Hardie Industries PLC", "JJSF": "J and J Snack Foods Corp.",
    "JKHY": "Jack Henry &amp; Associates", "JLL": "Jones Lang Lasalle Inc.", "JMSB": "John Marshall Bancorp Inc.",
    "JNJ": "Johnson &amp; Johnson", "JOBY": "Joby Aviation Inc. Class A", "JOE": "ST Joe",
    "JOUT": "Johnson Outdoors Inc. Class A", "JPM": "JPMorgan Chase", "JRVR": "James River Group Holdings Inc.",
    "JXN": "Jackson Financial Inc. Class A", "KAI": "Kadant Inc.", "KALU": "Kaiser Aluminium Corp.",
    "KALV": "Kalvista Pharmaceuticals Inc.", "KBH": "KB Home", "KBR": "Kbr Inc.",
    "KD": "Kyndryl Holdings Inc.", "KDP": "Keurig Dr Pepper", "KE": "Kimball Electronics Inc.",
    "KELYA": "Kelly Services Inc. Class A", "KEX": "Kirby Corp.", "KEY": "KeyCorp",
    "KEYS": "Keysight Technologies", "KFRC": "Kforce Inc.", "KFY": "Korn Ferry",
    "KGS": "Kodiak Gas Services Inc.", "KHC": "Kraft Heinz", "KIDS": "Orthopediatrics Corp.",
    "KIM": "Kimco Realty", "KKR": "KKR &amp; Co.", "KLAC": "KLA Corporation",
    "KLC": "Kindercare Learning Companies Inc.", "KLIC": "Kulicke and Soffa Industries Inc.", "KMB": "Kimberly-Clark",
    "KMI": "Kinder Morgan", "KMPR": "Kemper Corp.", "KMT": "Kennametal Inc.",
    "KMTS": "Kestra Medical Technologies LTD", "KMX": "Carmax Inc.", "KN": "Knowles Corp.",
    "KNF": "Knife River Corp.", "KNSL": "Kinsale Capital Group Inc.", "KNTK": "Kinetik Holdings Inc. Class A",
    "KNX": "Knight-swift Transportation Holdin", "KO": "Coca-Cola Company (The)", "KOD": "Kodiak Sciences Inc.",
    "KODK": "Eastman Kodak", "KOP": "Koppers Holdings Inc.", "KOPN": "Kopin Corp.",
    "KOS": "Kosmos Energy LTD", "KR": "Kroger", "KRC": "Kilroy Realty REIT Corp.",
    "KREF": "Kkr Real Estate Finance Inc. Trust", "KRG": "Kite Realty Group Trust REIT", "KRMN": "Karman Holdings Inc.",
    "KRNY": "Kearny Financial Corp.", "KROS": "Keros Therapeutics Inc.", "KRRO": "Korro Bio Inc.",
    "KRUS": "Kura Sushi USA Inc.", "KRYS": "Krystal Biotech Inc.", "KSS": "Kohls Corp.",
    "KTB": "Kontoor Brands Inc.", "KTOS": "Kratos Defense and Security Soluti", "KURA": "Kura Oncology Inc.",
    "KVUE": "Kenvue", "KW": "Kennedy Wilson Holdings Inc.", "KWR": "Quaker Houghton Corp.",
    "KYMR": "Kymera Therapeutics Inc.", "L": "Loews Corporation", "LAB": "Standard Biotools Inc.",
    "LAD": "Lithia Motors Inc. Class A", "LADR": "Ladder Capital Corp. Class A", "LAMR": "Lamar Advertising Company Clas",
    "LAND": "Gladstone Land REIT Corp.", "LASR": "Nlight Inc.", "LAUR": "Laureate Education Inc.",
    "LAW": "CS Disco Inc.", "LAZ": "Lazard Inc.", "LBRDA": "Liberty Broadband Corp. Series A",
    "LBRDK": "Liberty Broadband Corp. Series C", "LBRT": "Liberty Energy Inc. Class A", "LBTYA": "Liberty Global LTD Class A",
    "LBTYK": "Liberty Global LTD Class C", "LC": "Lendingclub Corp.", "LCID": "Lucid Group Inc.",
    "LCII": "Lci Industries", "LDOS": "Leidos", "LEA": "Lear Corp.",
    "LECO": "Lincoln Electric Holdings Inc.", "LEG": "Leggett & Platt Inc.", "LEN": "Lennar",
    "LENB": "Lennar Corp. Class B", "LENZ": "Lenz Therapeutics Inc.", "LEU": "Centrus Energy Corp. Class A",
    "LFST": "Lifestance Health Group Inc.", "LFUS": "Littelfuse Inc.", "LGIH": "Lgi Homes Inc.",
    "LGN": "Legence Corp. Class A", "LGND": "Ligand Pharmaceuticals Inc.", "LH": "Labcorp",
    "LHX": "L3Harris", "LIF": "Life360 Inc.", "LII": "Lennox International",
    "LILA": "Liberty Latin America LTD Class A", "LILAK": "Liberty Latin America LTD Class C", "LIN": "Linde plc",
    "LINC": "Lincoln Educational Services Corp.", "LIND": "Lindblad Expeditions Holdings Inc.", "LINE": "Lineage Inc.",
    "LION": "Lionsgate Studios Corp.", "LITE": "Lumentum Holdings Inc.", "LIVN": "Livanova PLC",
    "LKFN": "Lakeland Financial Corp.", "LKQ": "Lkq Corp.", "LLY": "Lilly (Eli)",
    "LLYVA": "Liberty Live Holdings Inc.", "LLYVK": "Liberty Live Holdings Inc.", "LMAT": "Lemaitre Vascular Inc.",
    "LMB": "Limbach Holdings Inc.", "LMND": "Lemonade Inc.", "LMNR": "Limoneira",
    "LMT": "Lockheed Martin", "LNC": "Lincoln National Corp.", "LNG": "Cheniere Energy Inc.",
    "LNN": "Lindsay Corp.", "LNT": "Alliant Energy", "LNTH": "Lantheus Holdings Inc.",
    "LOAR": "Loar Holdings Inc.", "LOB": "Live Oak Bancshares Inc.", "LOCO": "EL Pollo Loco Inc.",
    "LOPE": "Grand Canyon Education Inc.", "LOVE": "Lovesac Company", "LOW": "Lowe's",
    "LPG": "Dorian Lpg LTD", "LPLA": "Lpl Financial Holdings Inc.", "LPRO": "Open Lending Corp.",
    "LPX": "Louisiana Pacific Corp.", "LQDA": "Liquidia Corp.", "LQDT": "Liquidity Services Inc.",
    "LRCX": "Lam Research", "LRMR": "Larimar Therapeutics Inc.", "LRN": "Stride Inc.",
    "LSCC": "Lattice Semiconductor Corp.", "LSTR": "Landstar System Inc.", "LTC": "Ltc Properties REIT Inc.",
    "LTH": "Life Time Group Holdings Inc.", "LULU": "Lululemon Athletica", "LUMN": "Lumen Technologies Inc.",
    "LUNG": "Pulmonx Corp.", "LUNR": "Intuitive Machines Inc. Class A", "LUV": "Southwest Airlines",
    "LVS": "Las Vegas Sands", "LW": "Lamb Weston", "LXEO": "Lexeo Therapeutics Inc.",
    "LXFR": "Luxfer Holdings PLC", "LXP": "Lxp Industrial Trust", "LXU": "Lsb Industries Inc.",
    "LYB": "LyondellBasell", "LYFT": "Lyft Inc. Class A", "LYTS": "Lsi Industries Inc.",
    "LYV": "Live Nation Entertainment", "LZ": "Legalzoom Com Inc.", "LZB": "La-z-boy Inc.",
    "M": "Macys Inc.", "MA": "Mastercard", "MAA": "Mid-America Apartment Communities",
    "MAC": "Macerich REIT", "MAMA": "Mamas Creations Inc.", "MAN": "Manpower Inc.",
    "MANH": "Manhattan Associates Inc.", "MAR": "Marriott International", "MARA": "Mara Holdings Inc.",
    "MAS": "Masco", "MASI": "Masimo Corp.", "MASS": "908 Devices Inc.",
    "MAT": "Mattel Inc.", "MATV": "Mativ Holdings Inc.", "MATW": "Matthews International Corp. Class",
    "MATX": "Matson Inc.", "MAX": "Mediaalpha Inc. Class A", "MAZE": "Maze Therapeutics Inc.",
    "MBC": "Masterbrand Inc.", "MBI": "Mbia Inc.", "MBIN": "Merchants Bancorp",
    "MBUU": "Malibu Boats Class A Inc.", "MBWM": "Mercantile Bank Corp.", "MBX": "Mbx Biosciences Inc.",
    "MC": "Moelis Class A", "MCB": "Metropolitan Bank Holding Corp.", "MCBS": "Metrocity Bankshares Inc.",
    "MCD": "McDonald's", "MCFT": "Mastercraft Boat Holdings Inc.", "MCHB": "Mechanics Bancorp Class A",
    "MCHP": "Microchip Technology", "MCK": "McKesson Corporation", "MCO": "Moody's Corporation",
    "MCRI": "Monarch Casino and Resort Inc.", "MCS": "The Marcus Corp.", "MCW": "Mister Car Wash Inc.",
    "MCY": "Mercury General Corp.", "MD": "Pediatrix Medical Group Inc.", "MDB": "Mongodb Inc. Class A",
    "MDGL": "Madrigal Pharmaceuticals Inc.", "MDLZ": "Mondelez International", "MDT": "Medtronic",
    "MDU": "Mdu Resources Group Inc.", "MDXG": "Mimedx Group Inc.", "MED": "Medifast Inc.",
    "MEDP": "Medpace Holdings Inc.", "MEG": "Montrose Environmental Grp Inc.", "MEI": "Methode Electronics Inc.",
    "MET": "MetLife", "META": "Meta Platforms", "METC": "Ramaco Resources Inc. Class A",
    "MFA": "Mfa Financial Inc.", "MGEE": "Mge Energy Inc.", "MGM": "MGM Resorts",
    "MGNI": "Magnite Inc.", "MGPI": "Mgp Ingredients Inc.", "MGRC": "Mcgrath Rent",
    "MGTX": "Meiragtx Holdings PLC", "MGY": "Magnolia Oil Gas Corp. Class A", "MHK": "Mohawk Industries Inc.",
    "MHO": "M I Homes Inc.", "MIAX": "Miami International Holdings Inc.", "MIDD": "Middleby Corp.",
    "MIR": "Mirion Technologies Inc. Class A", "MIRM": "Mirum Pharmaceuticals Inc.", "MITK": "Mitek Systems Inc.",
    "MKC": "McCormick &amp; Company", "MKL": "Markel Group Inc.", "MKSI": "Mks",
    "MKTX": "Marketaxess Holdings Inc.", "MLAB": "Mesa Laboratories Inc.", "MLI": "Mueller Industries Inc.",
    "MLKN": "Millerknoll Inc.", "MLM": "Martin Marietta Materials", "MLR": "Miller Industries Inc.",
    "MLYS": "Mineralys Therapeutics Inc.", "MMI": "Marcus & Millichap Inc.", "MMS": "Maximus Inc.",
    "MMSI": "Merit Medical Systems Inc.", "MNKD": "Mannkind Corp.", "MNRO": "Monro Inc.",
    "MNST": "Monster Beverage", "MNTK": "Montauk Renewables Inc.", "MO": "Altria",
    "MOD": "Modine Manufacturing", "MOGA": "Moog Inc. Class A", "MOH": "Molina Healthcare",
    "MORN": "Morningstar Inc.", "MOS": "Mosaic Company (The)", "MOV": "Movado Group Inc.",
    "MP": "MP Materials Corp. Class A", "MPB": "Mid Penn Bancorp Inc.", "MPC": "Marathon Petroleum",
    "MPT": "Medical Properties Trust REIT Inc.", "MPWR": "Monolithic Power Systems", "MQ": "Marqeta Inc. Class A",
    "MRCY": "Mercury Systems Inc.", "MRK": "Merck &amp; Co.", "MRNA": "Moderna",
    "MRP": "Millrose Properties Inc. Class A", "MRSH": "Marsh McLennan", "MRTN": "Marten Transport LTD",
    "MRVI": "Maravai Lifesciences Holdings Inc.", "MRVL": "Marvell Technology Inc.", "MRX": "Marex Group PLC",
    "MS": "Morgan Stanley", "MSA": "Msa Safety Inc.", "MSBI": "Midland States Bancorp Inc.",
    "MSCI": "MSCI Inc.", "MSEX": "Middlesex Water", "MSFT": "Microsoft",
    "MSGE": "Madison Square Garden Entertainmen", "MSGS": "Madison Square Garden Sports Corp.", "MSI": "Motorola Solutions",
    "MSM": "Msc Industrial Inc. Class A", "MSTR": "Strategy Inc. Class A", "MTB": "M&amp;T Bank",
    "MTCH": "Match Group", "MTD": "Mettler Toledo", "MTDR": "Matador Resources",
    "MTG": "Mgic Investment Corp.", "MTH": "Meritage Corp.", "MTN": "Vail Resorts Inc.",
    "MTRN": "Materion Corp.", "MTSI": "Macom Technology Solutions Inc.", "MTUS": "Metallus Inc.",
    "MTW": "Manitowoc Inc.", "MTX": "Minerals Technologies Inc.", "MTZ": "MasTec Inc.",
    "MU": "Micron Technology", "MUR": "Murphy Oil Corp.", "MUSA": "Murphy USA Inc.",
    "MVBF": "Mvb Financial Corp.", "MVIS": "Microvision Inc.", "MVST": "Microvast Holdings Inc.",
    "MWA": "Mueller Water Products Inc. Series", "MXCT": "Maxcyte Inc.", "MXL": "Maxlinear Inc.",
    "MYE": "Myers Industries Inc.", "MYGN": "Myriad Genetics Inc.", "MYPS": "Playstudios Inc. Class A",
    "MYRG": "Myr Group Inc.", "MZTI": "Marzetti", "NABL": "N Able Inc.",
    "NAGE": "Niagen Bioscience Inc.", "NAT": "Nordic American Tankers LTD", "NATL": "Ncr Atleos Corp.",
    "NAVI": "Navient Corp.", "NAVN": "Navan Inc. Class A", "NB": "Niocorp Developments LTD",
    "NBBK": "NB Bancorp Inc.", "NBHC": "National Bank Holdings Corp. Class", "NBIX": "Neurocrine Biosciences Inc.",
    "NBN": "Northeast Bank", "NBR": "Nabors Industries LTD", "NBTB": "Nbt Bancorp Inc.",
    "NCLH": "Norwegian Cruise Line Holdings", "NCMI": "National Cinemedia Inc.", "NCNO": "Ncino Inc.",
    "NDAQ": "Nasdaq, Inc.", "NDSN": "Nordson Corporation", "NE": "Noble Corporation PLC",
    "NECB": "Northeast Community Bancorp Inc.", "NEE": "NextEra Energy", "NEM": "Newmont",
    "NEO": "Neogenomics Inc.", "NEOG": "Neogen Corp.", "NESR": "National Energy Services Reunited",
    "NET": "Cloudflare Inc. Class A", "NEU": "Newmarket Corp.", "NEWT": "Newtekone Inc.",
    "NEXT": "Nextdecade Corp.", "NFBK": "Northfield Bancorp Inc.", "NFE": "New Fortress Energy Inc. Class A",
    "NFG": "National Fuel Gas", "NFLX": "Netflix", "NG": "Novagold Resources Inc.",
    "NGNE": "Neurogene Inc.", "NGVC": "Natural Grocers BY Vitamin Cottage", "NGVT": "Ingevity Corp.",
    "NHC": "National Healthcare Corp.", "NHI": "National Health Investors REIT Inc.", "NI": "NiSource",
    "NIC": "Nicolet Bankshares Inc.", "NIQ": "Niq Global Intelligence PLC", "NJR": "New Jersey Resources Corp.",
    "NKE": "Nike, Inc.", "NKTX": "Nkarta Inc.", "NLOP": "Net Lease Office Properties",
    "NLY": "Annaly Capital Management REIT Inc.", "NMIH": "Nmi Holdings Inc.", "NMRK": "Newmark Group Inc. Class A",
    "NN": "Nextnav Inc.", "NNE": "Nano Nuclear Energy Inc.", "NNI": "Nelnet Inc. Class A",
    "NNN": "Nnn REIT Inc.", "NNOX": "Nano X Imaging LTD", "NOC": "Northrop Grumman",
    "NOG": "Northern Oil and Gas Inc.", "NOV": "Nov Inc.", "NOVT": "Novanta Inc.",
    "NOW": "ServiceNow", "NPCE": "Neuropace Inc.", "NPK": "National Presto Industries Inc.",
    "NPKI": "Npk International Inc.", "NPO": "Enpro Inc.", "NRC": "National Research Corp.",
    "NRDS": "Nerdwallet Inc. Class A", "NRG": "NRG Energy", "NRIM": "Northrim Bancorp Inc.",
    "NRIX": "Nurix Therapeutics Inc.", "NSA": "National Storage Affiliates Trust", "NSC": "Norfolk Southern",
    "NSIT": "Insight Enterprises Inc.", "NSP": "Insperity Inc.", "NSSC": "Napco Security Technologies Inc.",
    "NTAP": "NetApp", "NTB": "Bank of NT Butterfield & Son LTD", "NTCT": "Netscout Systems Inc.",
    "NTGR": "Netgear Inc.", "NTLA": "Intellia Therapeutics Inc.", "NTNX": "Nutanix Inc. Class A",
    "NTRA": "Natera Inc.", "NTRS": "Northern Trust", "NTST": "Netstreit Corp.",
    "NU": "NU Holdings LTD Class A", "NUE": "Nucor", "NUS": "NU Skin Enterprises Inc. Class A",
    "NUTX": "Nutex Health Inc.", "NUVB": "Nuvation Bio Inc. Class A", "NUVL": "Nuvalent Inc. Class A",
    "NVAX": "Novavax Inc.", "NVCR": "Novocure LTD", "NVDA": "Nvidia",
    "NVEC": "Nve Corp.", "NVR": "NVR, Inc.", "NVRI": "Enviri Corp.",
    "NVST": "Envista Holdings Corp.", "NVT": "Nvent Electric PLC", "NVTS": "Navitas Semiconductor Corp.",
    "NWBI": "Northwest Bancshares Inc.", "NWE": "Northwestern Energy Group Inc.", "NWL": "Newell Brands Inc.",
    "NWN": "Northwest Natural Holding Company", "NWPX": "Nwpx Infrastructure Inc.", "NWS": "News Corp (Class B)",
    "NWSA": "News Corp (Class A)", "NX": "Quanex Building Products Corp.", "NXDR": "Nextdoor Holdings Inc. Class A",
    "NXDT": "Nexpoint Diversified Real Estate T", "NXPI": "NXP Semiconductors", "NXRT": "Nexpoint Residential Trust Inc.",
    "NXST": "Nexstar Media Group Inc.", "NXT": "Nextpower Inc. Class A", "NYT": "New York Times Class A",
    "O": "Realty Income", "OABI": "Omniab Inc.", "OBK": "Origin Bancorp Inc.",
    "OBT": "Orange County Bancorp Inc.", "OC": "Owens Corning", "OCFC": "Oceanfirst Financial Corp.",
    "OCUL": "Ocular Therapeutix Inc.", "ODC": "Oil Dri Corporation of America", "ODFL": "Old Dominion",
    "OEC": "Orion SA", "OFG": "Ofg Bancorp", "OFIX": "Orthofix Medical Inc.",
    "OFLX": "Omega Flex Inc.", "OGE": "Oge Energy Corp.", "OGN": "Organon",
    "OGS": "One Gas Inc.", "OHI": "Omega Healthcare Investors REIT IN", "OI": "O I Glass Inc.",
    "OII": "Oceaneering International Inc.", "OIS": "Oil States International Inc.", "OKE": "Oneok",
    "OKLO": "Oklo Inc. Class A", "OKTA": "Okta Inc. Class A", "OLED": "Universal Display Corp.",
    "OLLI": "Ollies Bargain Outlet Holdings Inc.", "OLMA": "Olema Pharmaceuticals Inc.", "OLN": "Olin Corp.",
    "OLP": "One Liberty Properties REIT Inc.", "OLPX": "Olaplex Holdings Inc.", "OMC": "Omnicom Group",
    "OMCL": "Omnicell Inc.", "OMER": "Omeros Corp.", "OMF": "Onemain Holdings Inc.",
    "ON": "ON Semiconductor", "ONB": "Old National Bancorp", "ONEW": "Onewater Marine Class A Inc.",
    "ONIT": "Onity Group Inc.", "ONON": "ON Holding LTD Class A", "ONTF": "On24 Inc.",
    "ONTO": "Onto Innovation Inc.", "OOMA": "Ooma Inc.", "OPCH": "Option Care Health Inc.",
    "OPK": "Opko Health Inc.", "OPLN": "Openlane Inc.", "OPRX": "Optimizerx Corp.",
    "OPTU": "Optimum Communications Inc. Class A", "ORA": "Ormat Tech Inc.", "ORC": "Orchid Island Capital Inc.",
    "ORCL": "Oracle Corporation", "ORGO": "Organogenesis Holdings Inc. Class A", "ORI": "Old Republic International Corp.",
    "ORIC": "Oric Pharmaceuticals Inc.", "ORKA": "Oruka Therapeutics Inc.", "ORLY": "O’Reilly Automotive",
    "ORRF": "Orrstown Financial Services Inc.", "OSBC": "Old Second Bancorp Inc.", "OSCR": "Oscar Health Inc. Class A",
    "OSG": "Octave Specialty Group Inc.", "OSIS": "Osi Systems Inc.", "OSK": "Oshkosh Corp.",
    "OSPN": "Onespan Inc.", "OSUR": "Orasure Technologies Inc.", "OSW": "Onespaworld Holdings LTD",
    "OTIS": "Otis Worldwide", "OTTR": "Otter Tail Corp.", "OUST": "Ouster Inc.",
    "OUT": "Outfront Media Inc.", "OVV": "Ovintiv Inc.", "OWL": "Blue Owl Capital Inc. Class A",
    "OXM": "Oxford Industries Inc.", "OXY": "Occidental Petroleum", "OZK": "Bank Ozk",
    "PACB": "Pacific Biosciences of California", "PACK": "Ranpak Holdings Corp. Class A", "PACS": "Pacs Group Inc.",
    "PAG": "Penske Automotive Group Voting Inc.", "PAGS": "Pagseguro Digital LTD Class A", "PAHC": "Phibro Animal Health Corp. Class A",
    "PANL": "Pangaea Logistics Solutions LTD", "PANW": "Palo Alto Networks", "PAR": "Par Technology Corp.",
    "PARR": "Par Pacific Holdings Inc.", "PATH": "Uipath Inc. Class A", "PATK": "Patrick Industries Inc.",
    "PAX": "Patria Investments LTD Class A", "PAYC": "Paycom", "PAYO": "Payoneer Global Inc.",
    "PAYS": "Paysign Inc.", "PAYX": "Paychex", "PB": "Prosperity Bancshares Inc.",
    "PBF": "Pbf Energy Inc. Class A", "PBH": "Prestige Consumer Healthcare Inc.", "PBI": "Pitney Bowes Inc.",
    "PCAR": "Paccar", "PCG": "PG&amp;E Corporation", "PCOR": "Procore Technologies Inc.",
    "PCRX": "Pacira Biosciences Inc.", "PCT": "Purecycle Technologies Inc.", "PCTY": "Paylocity Holding Corp.",
    "PCVX": "Vaxcyte Inc.", "PD": "Pagerduty Inc.", "PDFS": "Pdf Solutions Inc.",
    "PDM": "Piedmont Realty Trust Inc. Class A", "PEB": "Pebblebrook Hotel Trust REIT", "PEBO": "Peoples Bancorp Inc.",
    "PECO": "Phillips Edison and Company Inc.", "PEG": "Public Service Enterprise Group", "PEGA": "Pegasystems Inc.",
    "PEN": "Penumbra Inc.", "PENG": "Penguin Solutions Inc.", "PENN": "Penn Entertainment Inc.",
    "PEP": "PepsiCo", "PFBC": "Preferred Bank", "PFE": "Pfizer",
    "PFG": "Principal Financial Group", "PFGC": "Performance Food Group", "PFIS": "Peoples Financial Services Corp.",
    "PFS": "Provident Financial Services Inc.", "PFSI": "Pennymac Financial Services Inc.", "PG": "Procter &amp; Gamble",
    "PGC": "Peapack Gladstone Financial Corp.", "PGEN": "Precigen Inc.", "PGNY": "Progyny Inc.",
    "PGR": "Progressive Corporation", "PGY": "Pagaya Technologies LTD Class A", "PH": "Parker Hannifin",
    "PHAT": "Phathom Pharmaceuticals Inc.", "PHIN": "Phinia Inc.", "PHM": "PulteGroup",
    "PHR": "Phreesia Inc.", "PI": "Impinj Inc.", "PII": "Polaris Inc.",
    "PINS": "Pinterest Inc. Class A", "PIPR": "Piper Sandler Companies", "PJT": "Pjt Partners Inc. Class A",
    "PK": "Park Hotels Resorts Inc.", "PKE": "Park Aerospace Corp.", "PKG": "Packaging Corporation of America",
    "PKST": "Peakstone Realty Trust Class E", "PL": "Planet Labs Class A", "PLAB": "Photronics Inc.",
    "PLAY": "Dave and Busters Entertainment Inc.", "PLD": "Prologis", "PLMR": "Palomar Holdings Inc.",
    "PLNT": "Planet Fitness Inc. Class A", "PLOW": "Douglas Dynamics Inc.", "PLPC": "Preformed Line Products",
    "PLSE": "Pulse Biosciences Inc.", "PLTK": "Playtika Holding Corp.", "PLTR": "Palantir Technologies",
    "PLUG": "Plug Power Inc.", "PLUS": "Eplus", "PLXS": "Plexus Corp.",
    "PM": "Philip Morris International", "PMT": "Pennymac Mortgage Investment Trust", "PNC": "PNC Financial Services",
    "PNFP": "Pinnacle Financial Partners Inc.", "PNR": "Pentair", "PNTG": "Pennant Group Inc.",
    "PNW": "Pinnacle West Capital", "PODD": "Insulet Corporation", "POOL": "Pool Corporation",
    "POR": "Portland General Electric", "POST": "Post Holdings Inc.", "POWI": "Power Integrations Inc.",
    "POWL": "Powell Industries Inc.", "POWW": "Outdoor Holding", "PPC": "Pilgrims Pride Corp.",
    "PPG": "PPG Industries", "PPL": "PPL Corporation", "PPTA": "Perpetua Resources Corp.",
    "PR": "Permian Resources Corp. Class A", "PRA": "Proassurance Corp.", "PRAA": "Pra Group Inc.",
    "PRAX": "Praxis Precision Medicines Inc.", "PRCH": "Porch Group Inc.", "PRCT": "Procept Biorobotics Corp.",
    "PRDO": "Perdoceo Education Corp.", "PRG": "Prog Holdings Inc.", "PRGO": "Perrigo PLC",
    "PRGS": "Progress Software Corp.", "PRI": "Primerica Inc.", "PRIM": "Primoris Services Corp.",
    "PRK": "Park National Corp.", "PRKS": "United Parks and Resorts Inc.", "PRLB": "Proto Labs Inc.",
    "PRM": "Perimeter Solutions Inc.", "PRMB": "Primo Brands Class A Corp.", "PRME": "Prime Medicine Inc.",
    "PRSU": "Pursuit Attractions and Hospitalit", "PRTA": "Prothena PLC", "PRTH": "Priority Technology Holdings Inc.",
    "PRU": "Prudential Financial", "PRVA": "Privia Health Group Inc.", "PSA": "Public Storage",
    "PSFE": "Paysafe LTD", "PSIX": "Power Solutions International Inc.", "PSKY": "Paramount Skydance Corporation",
    "PSMT": "Pricesmart Inc.", "PSN": "Parsons Corp.", "PSTG": "Everpure Inc. Class A",
    "PSTL": "Postal Realty Trust Inc. Class A", "PSX": "Phillips 66", "PTC": "PTC Inc.",
    "PTCT": "Ptc Therapeutics Inc.", "PTEN": "Patterson Uti Energy Inc.", "PTGX": "Protagonist Therapeutics Inc.",
    "PTLO": "Portillo S Inc. Class A", "PTON": "Peloton Interactive Class A Inc.", "PUBM": "Pubmatic Inc. Class A",
    "PUMP": "Propetro Holding Corp.", "PVH": "Pvh Corp.", "PVLA": "Palvella Therapeutics Inc.",
    "PWP": "Perella Weinberg Partners Class A", "PWR": "Quanta Services Inc.", "PYPL": "PayPal",
    "PZZA": "Papa Johns International Inc.", "Q": "Qnity Electronics", "QBTS": "D Wave Quantum Inc.",
    "QCOM": "Qualcomm", "QCRH": "Qcr Holdings Inc.", "QDEL": "Quidelortho Corp.",
    "QGEN": "Qiagen NV", "QLYS": "Qualys Inc.", "QNST": "Quinstreet Inc.",
    "QRTEA": "Qurate Retail Group", "QRVO": "Qorvo Inc.", "QS": "Quantumscape Corp. Class A",
    "QSI": "Quantum SI Inc. Class A", "QSR": "Restaurants Brands International I", "QTRX": "Quanterix Corp.",
    "QTWO": "Q2 Holdings Inc.", "QUBT": "Quantum Computing Inc.", "QXO": "Qxo Inc.",
    "R": "Ryder System Inc.", "RAL": "Ralliant Corp.", "RAMP": "Liveramp Holdings Inc.",
    "RAPP": "Rapport Therapeutics Inc.", "RARE": "Ultragenyx Pharmaceutical Inc.", "RBA": "RB Global Inc.",
    "RBB": "Rbb Bancorp", "RBBN": "Ribbon Communications Inc.", "RBC": "Rbc Bearings Inc.",
    "RBCAA": "Republic Bancorp Inc. Class A", "RBLX": "Roblox Corp. Class A", "RBRK": "Rubrik Inc. Class A",
    "RC": "Ready Capital Corp.", "RCAT": "Red Cat Holdings Inc.", "RCEL": "Avita Medical Inc.",
    "RCKT": "Rocket Pharmaceuticals Inc.", "RCL": "Royal Caribbean Group", "RCUS": "Arcus Biosciences Inc.",
    "RDDT": "Reddit Inc. Class A", "RDN": "Radian Group Inc.", "RDNT": "Radnet Inc.",
    "RDVT": "Red Violet Inc.", "RDW": "Redwire Corp.", "REAL": "The Realreal Inc.",
    "REAX": "Real Brokerage Inc.", "REFI": "Chicago Atlantic Real Estate Finan", "REG": "Regency Centers",
    "REGN": "Regeneron Pharmaceuticals", "RELY": "Remitly Global Inc.", "REPL": "Replimune Group Inc.",
    "REPX": "Riley Exploration Permian Inc.", "RES": "Rpc Inc.", "REX": "Rex American Resources Corp.",
    "REXR": "Rexford Industrial Realty REIT Inc.", "REYN": "Reynolds Consumer Products Inc.", "REZI": "Resideo Technologies Inc.",
    "RF": "Regions Financial Corporation", "RGA": "Reinsurance Group of America Inc.", "RGEN": "Repligen Corp.",
    "RGLD": "Royal Gold Inc.", "RGNX": "Regenxbio Inc.", "RGP": "Resources Connection Inc.",
    "RGR": "Sturm Ruger Inc.", "RGTI": "Rigetti Computing Inc.", "RHI": "Robert Half",
    "RHLD": "Resolute Holdings Management Inc.", "RHP": "Ryman Hospitality Properties REIT", "RICK": "Rci Hospitality Holdings Inc.",
    "RIG": "Transocean LTD", "RIGL": "Rigel Pharmaceuticals Inc.", "RIOT": "Riot Platforms Inc.",
    "RITM": "Rithm Capital Corp.", "RIVN": "Rivian Automotive Inc. Class A", "RJF": "Raymond James Financial",
    "RKLB": "Rocket Lab Corp.", "RKT": "Rocket Companies Inc. Class A", "RL": "Ralph Lauren Corporation",
    "RLAY": "Relay Therapeutics Inc.", "RLI": "Rli Corp.", "RLJ": "Rlj Lodging Trust REIT",
    "RM": "Regional Management Corp.", "RMAX": "RE Max Holdings Inc. Class A", "RMBS": "Rambus Inc.",
    "RMD": "ResMed", "RMNI": "Rimini Street Inc.", "RMR": "Rmr Group Inc. Class A",
    "RNA": "Atrium Therapeutics Inc.", "RNG": "Ringcentral Inc. Class A", "RNR": "Renaissancere Holding LTD",
    "RNST": "Renasant Corp.", "ROAD": "Construction Partners Inc. Class A", "ROCK": "Gibraltar Industries Inc.",
    "ROG": "Rogers Corp.", "ROIV": "Roivant Sciences LTD", "ROK": "Rockwell Automation",
    "ROKU": "Roku Inc. Class A", "ROL": "Rollins, Inc.", "ROOT": "Root Inc. Class A",
    "ROP": "Roper Technologies", "ROST": "Ross Stores", "RPAY": "Repay Holdings Corp. Class A",
    "RPC": "Ridgepost Capital Inc. Class A", "RPD": "Rapid7 Inc.", "RPM": "Rpm International Inc.",
    "RPRX": "Royalty Pharma PLC Class A", "RRBI": "Red River Bancshares Inc.", "RRC": "Range Resources Corp.",
    "RRR": "Red Rock Resorts Ors Class A Inc.", "RRX": "Regal Rexnord Corp.", "RS": "Reliance Steel & Aluminum",
    "RSG": "Republic Services", "RSI": "Rush Street Interactive Inc. Class", "RTX": "RTX Corporation",
    "RUM": "Rumble Inc. Class A", "RUN": "Sunrun Inc.", "RUSHA": "Rush Enterprises Inc. Class A",
    "RUSHB": "Rush Enterprises Inc. Class B", "RVLV": "Revolve Group Class A Inc.", "RVMD": "Revolution Medicines Inc.",
    "RVTY": "Revvity", "RWT": "Redwood Trust REIT Inc.", "RXO": "Rxo Inc.",
    "RXRX": "Recursion Pharmaceuticals Inc. Clas", "RXST": "Rxsight Inc.", "RYAM": "Rayonier Advanced Materials Inc.",
    "RYAN": "Ryan Specialty Holdings Inc. Class", "RYN": "Rayonier REIT Inc.", "RYTM": "Rhythm Pharmaceuticals Inc.",
    "RYZ": "Ryerson Holding Corp.", "RZLV": "Rezolve AI PLC", "S": "Sentinelone Inc. Class A",
    "SABR": "Sabre Corp.", "SAFE": "Safehold Inc.", "SAFT": "Safety Insurance Group Inc.",
    "SAH": "Sonic Automotive Inc. Class A", "SAIA": "Saia Inc.", "SAIC": "Science Applications International",
    "SAIL": "Sailpoint Inc.", "SAM": "Boston Beer Inc. Class A", "SANA": "Sana Biotechnology Inc.",
    "SANM": "Sanmina Corp.", "SARO": "Standardaero", "SATS": "Echostar Corp. Class A",
    "SB": "Safe Bulkers Inc.", "SBAC": "SBA Communications", "SBCF": "Seacoast Banking of Florida",
    "SBGI": "Sinclair Inc. Class A", "SBH": "Sally Beauty Holdings Inc.", "SBRA": "Sabra Health Care REIT Inc.",
    "SBSI": "Southside Bancshares Inc.", "SBUX": "Starbucks", "SCCO": "Southern Copper Corp.",
    "SCHL": "Scholastic Corp.", "SCHW": "Charles Schwab Corporation", "SCI": "Service",
    "SCL": "Stepan", "SCSC": "Scansource Inc.", "SCVL": "Shoe Carnival Inc.",
    "SD": "Sandridge Energy Inc.", "SDGR": "Schrodinger Inc.", "SDRL": "Seadrill LTD",
    "SEAT": "Vivid Seats Inc. Class A", "SEB": "Seaboard Corp.", "SEE": "Sealed Air Corp.",
    "SEG": "Seaport Entertainment Group Inc.", "SEI": "Solaris Oilfield Infrastructure IN", "SEIC": "Sei Investments",
    "SEM": "Select Medical Holdings Corp.", "SEMR": "Semrush Holdings Inc. Class A", "SENEA": "Seneca Foods Corp. Class A",
    "SEPN": "Septerna Inc.", "SERV": "Serve Robotics Inc.", "SEZL": "Sezzle Inc.",
    "SF": "Stifel Financial Corp.", "SFBS": "Servisfirst Bancshares Inc.", "SFD": "Smithfield Foods Inc.",
    "SFIX": "Stitch Fix Inc. Class A", "SFL": "Sfl LTD", "SFM": "Sprouts Farmers Market Inc.",
    "SFNC": "Simmons First National Corp. Class", "SFST": "Southern First Bancshares Inc.", "SG": "Sweetgreen Inc. Class A",
    "SGHC": "Super Group LTD", "SGI": "Somnigroup International Inc.", "SGRY": "Surgery Partners Inc.",
    "SHAK": "Shake Shack Inc. Class A", "SHBI": "Shore Bancshares Inc.", "SHC": "Sotera Health Company",
    "SHEN": "Shenandoah Telecommunications", "SHLS": "Shoals Technologies Group Inc. Clas", "SHO": "Sunstone Hotel Investors REIT Inc.",
    "SHOO": "Steven Madden LTD", "SHW": "Sherwin-Williams", "SIBN": "SI Bone Inc.",
    "SIG": "Signet Jewelers LTD", "SIGA": "Siga Technologies Inc.", "SIGI": "Selective Insurance Group Inc.",
    "SILA": "Sila Rlty TR Inc. Trust", "SION": "Sionna Therapeutics Inc.", "SIRI": "Siriusxm Holdings Inc.",
    "SITC": "Site Centers Corp.", "SITE": "Siteone Landscape Supply Inc.", "SITM": "Sitime Corp.",
    "SJM": "J.M. Smucker Company (The)", "SKIN": "Beauty Health Company Class A Clas", "SKT": "Tanger Inc.",
    "SKWD": "Skyward Specialty Insurance Group", "SKY": "Champion Homes Inc.", "SKYT": "Skywater Technology Inc.",
    "SKYW": "Skywest Inc.", "SLAB": "Silicon Laboratories Inc.", "SLB": "Schlumberger",
    "SLDE": "Slide Insurance Holdings Inc.", "SLDP": "Solid Power Inc. Class A", "SLG": "SL Green Realty REIT Corp.",
    "SLGN": "Silgan Holdings Inc.", "SLM": "Slm Corp.", "SLNO": "Soleno Therapeutics Inc.",
    "SLP": "Simulations Plus Inc.", "SLQT": "Selectquote Inc.", "SLS": "Sellas Life Sciences Group Inc.",
    "SLVM": "Sylvamo Corp.", "SM": "SM Energy", "SMA": "Smartstop Self Storage REIT Inc.",
    "SMBC": "Southern Missouri Bancorp Inc.", "SMBK": "Smartfinancial Inc.", "SMCI": "Supermicro",
    "SMG": "Scotts Miracle Gro", "SMMT": "Summit Therapeutics Inc.", "SMP": "Standard Motor Products Inc.",
    "SMPL": "The Simply Good Foods Company", "SMR": "Nuscale Power Corp. Class A", "SMTC": "Semtech Corp.",
    "SN": "Sharkninja Inc.", "SNA": "Snap-on", "SNBR": "Sleep Number Corp.",
    "SNCY": "Sun Country Airlines Holdings Inc.", "SNDK": "Sandisk", "SNDR": "Schneider National Inc. Class B",
    "SNDX": "Syndax Pharmaceuticals Inc.", "SNEX": "Stonex Group Inc.", "SNOW": "Snowflake Inc.",
    "SNPS": "Synopsys", "SNX": "TD Synnex Corp.", "SO": "Southern Company",
    "SOC": "Sable Offshore Corp. Class A", "SOFI": "Sofi Technologies Inc.", "SOLS": "Solstice Advanced Materials Inc.",
    "SOLV": "Solventum", "SON": "Sonoco Products", "SONO": "Sonos Inc.",
    "SOUN": "Soundhound AI Inc. Class A", "SPB": "Spectrum Brands Holdings Inc.", "SPFI": "South Plains Financial Inc.",
    "SPG": "Simon Property Group", "SPGI": "S&amp;P Global", "SPHR": "Sphere Entertainment Class A",
    "SPNT": "Siriuspoint LTD", "SPOK": "Spok Holdings Inc.", "SPOT": "Spotify Technology SA",
    "SPRY": "Ars Pharmaceuticals Inc.", "SPSC": "Sps Commerce Inc.", "SPT": "Sprout Social Inc. Class A",
    "SPXC": "Spx Technologies Inc.", "SR": "Spire Inc.", "SRCE": "1st Source Corp.",
    "SRE": "Sempra", "SRPT": "Sarepta Therapeutics Inc.", "SRRK": "Scholar Rock Holding Corp.",
    "SRTA": "Strata Critical Medical Inc. Class", "SSB": "Southstate Bank Corp.", "SSD": "Simpson Manufacturing Inc.",
    "SSNC": "SS and C Technologies Holdings Inc.", "SSP": "EW Scripps Class A", "SSRM": "Ssr Mining Inc.",
    "SSTI": "Soundthinking Inc.", "SSTK": "Shutterstock Inc.", "ST": "Sensata Technologies Holding PLC",
    "STAA": "Staar Surgical", "STAG": "Stag Industrial REIT Inc.", "STBA": "S and T Bancorp Inc.",
    "STC": "Stewart Info Services Corp.", "STE": "Steris", "STEL": "Stellar Bancorp Inc.",
    "STEP": "Stepstone Group Inc. Class A", "STGW": "Stagwell Inc. Class A", "STKL": "Sunopta Inc.",
    "STLD": "Steel Dynamics", "STNE": "Stoneco LTD Class A", "STNG": "Scorpio Tankers Inc.",
    "STOK": "Stoke Therapeutics Inc.", "STRA": "Strategic Education Inc.", "STRL": "Sterling Infrastructure Inc.",
    "STRZ": "Starz Entertainment Corp.", "STT": "State Street Corporation", "STWD": "Starwood Property Trust REIT Inc.",
    "STX": "Seagate Technology", "STZ": "Constellation Brands", "SUI": "Sun Communities REIT Inc.",
    "SUNS": "Sunrise Realty Trust Inc.", "SUPN": "Supernus Pharmaceuticals Inc.", "SVC": "Service Properties Trust",
    "SVRA": "Savara Inc.", "SVV": "Savers Value Village Inc.", "SW": "Smurfit Westrock",
    "SWBI": "Smith Wesson Brands Inc.", "SWK": "Stanley Black &amp; Decker", "SWKS": "Skyworks Solutions",
    "SWX": "Southwest Gas Holdings Inc.", "SXC": "Suncoke Energy Inc.", "SXI": "Standex International Corp.",
    "SXT": "Sensient Technologies Corp.", "SYBT": "Stock Yards Bancorp Inc.", "SYF": "Synchrony Financial",
    "SYK": "Stryker Corporation", "SYNA": "Synaptics Inc.", "SYRE": "Spyre Therapeutics Inc.",
    "SYY": "Sysco", "T": "AT&amp;T", "TALK": "Talkspace Inc.",
    "TALO": "Talos Energy Inc.", "TAP": "Molson Coors Beverage Company", "TARS": "Tarsus Pharmaceuticals Inc.",
    "TBBK": "Bancorp Inc.", "TBCH": "Turtle Beach Corp.", "TBI": "Trueblue Inc.",
    "TBPH": "Theravance Biopharma Inc.", "TCBI": "Texas Capital Bancshares Inc.", "TCBK": "Trico Bancshares",
    "TCBX": "Third Coast Bancshares Inc.", "TCMD": "Tactile Systems Technology Inc.", "TCX": "Tucows Inc.",
    "TDAY": "USA Today Inc.", "TDC": "Teradata Corp.", "TDG": "TransDigm Group",
    "TDOC": "Teladoc Health Inc.", "TDS": "Telephone and Data Systems Inc.", "TDUP": "Thredup Inc. Class A",
    "TDW": "Tidewater Inc.", "TDY": "Teledyne Technologies", "TE": "T1 Energy Inc.",
    "TEAD": "Teads Holding", "TEAM": "Atlassian Corp. Class A", "TECH": "Bio-Techne",
    "TEL": "TE Connectivity", "TEM": "Tempus AI Inc. Class A", "TENB": "Tenable Holdings Inc.",
    "TER": "Teradyne", "TERN": "Terns Pharmaceuticals Inc.", "TEX": "Terex Corp.",
    "TFC": "Truist Financial", "TFIN": "Triumph Financial Inc.", "TFSL": "Tfs Financial Corp.",
    "TFX": "Teleflex Inc.", "TG": "Tredegar Corp.", "TGLS": "Tecnoglass Inc.",
    "TGNA": "Tegna Inc.", "TGT": "Target Corporation", "TGTX": "TG Therapeutics Inc.",
    "TH": "Target Hospitality Corp.", "THC": "Tenet Healthcare Corp.", "THFF": "First Financial Corporation Corp.",
    "THG": "Hanover Insurance Group Inc.", "THO": "Thor Industries Inc.", "THR": "Thermon Group Holdings Inc.",
    "THRD": "Third Harmonic Bio Inc.", "THRM": "Gentherm Inc.", "THRY": "Thryv Holdings Inc.",
    "TIC": "Tic Solutions Inc.", "TIGO": "Millicom International Cellular SA", "TILE": "Interface Inc.",
    "TIPT": "Tiptree Inc.", "TITN": "Titan Machinery Inc.", "TJX": "TJX Companies",
    "TK": "Teekay Corporation Corp. LTD", "TKO": "TKO Group Holdings", "TKR": "Timken",
    "TLN": "Talen Energy Corp.", "TMCI": "Treace Medical Concepts Inc.", "TMDX": "Transmedics Group Inc.",
    "TMHC": "Taylor Morrison Home Corp.", "TMO": "Thermo Fisher Scientific", "TMP": "Tompkins Financial Corp.",
    "TMUS": "T-Mobile US", "TNC": "Tennant", "TNDM": "Tandem Diabetes Care Inc.",
    "TNET": "Trinet Group Incinary", "TNGX": "Tango Therapeutics Inc.", "TNK": "Teekay Tankers LTD Class A",
    "TNL": "Travel Leisure", "TOL": "Toll Brothers Inc.", "TOST": "Toast Inc. Class A",
    "TOWN": "Townebank", "TPB": "Turning Point Brands Inc.", "TPC": "Tutor Perini Corp.",
    "TPG": "Tpg Inc. Class A", "TPH": "Tri Pointe Homes Inc.", "TPL": "Texas Pacific Land Corporation",
    "TPR": "Tapestry, Inc.", "TR": "Tootsie Roll Industries Inc.", "TRC": "Tejon Ranch",
    "TRDA": "Entrada Therapeutics Inc.", "TREE": "Lendingtree Inc.", "TREX": "Trex Inc.",
    "TRGP": "Targa Resources", "TRIP": "Tripadvisor Inc.", "TRMB": "Trimble Inc.",
    "TRMK": "Trustmark Corp.", "TRN": "Trinity Industries Inc.", "TRNO": "Terreno Realty REIT Corp.",
    "TRNS": "Transcat Inc.", "TROW": "T. Rowe Price", "TROX": "Tronox Holdings PLC",
    "TRS": "Trimas Corp.", "TRST": "Trustco Bank Corp.", "TRTX": "Tpg RE Finance Trust Inc.",
    "TRU": "Transunion", "TRUP": "Trupanion Inc.", "TRV": "Travelers Companies (The)",
    "TRVI": "Trevi Therapeutics Inc.", "TSBK": "Timberland Bancorp Inc.", "TSCO": "Tractor Supply",
    "TSHA": "Taysha Gene Therapies Inc.", "TSLA": "Tesla, Inc.", "TSN": "Tyson Foods",
    "TT": "Trane Technologies", "TTC": "Toro", "TTD": "Trade Desk (The)",
    "TTEC": "Ttec Holdings Inc.", "TTEK": "Tetra Tech Inc.", "TTGT": "Techtarget Inc.",
    "TTI": "Tetra Technologies Inc.", "TTMI": "Ttm Technologies Inc.", "TTWO": "Take-Two Interactive",
    "TVTX": "Travere Therapeutics Inc.", "TW": "Tradeweb Markets Inc. Class A", "TWI": "Titan International Inc.",
    "TWLO": "Twilio Inc. Class A", "TWO": "Two Harbors Investment Corp.", "TWST": "Twist Bioscience Corp.",
    "TXG": "10x Genomics Inc. Class A", "TXN": "Texas Instruments", "TXNM": "Txnm Energy Inc.",
    "TXRH": "Texas Roadhouse Inc.", "TXT": "Textron", "TYL": "Tyler Technologies",
    "TYRA": "Tyra Biosciences Inc.", "U": "Unity Software Inc.", "UA": "Under Armour Inc. Class C",
    "UAA": "Under Armour Inc. Class A", "UAL": "United Airlines Holdings", "UAMY": "United States Antimony Corp.",
    "UBSI": "United Bankshares Inc.", "UCB": "United Community Banks Inc.", "UCTT": "Ultra Clean Holdings Inc.",
    "UDMY": "Udemy Inc.", "UDR": "UDR, Inc.", "UE": "Urban Edge Properties",
    "UEC": "Uranium Energy Corp.", "UFCS": "United Fire Group Inc.", "UFPI": "Ufp Industries Inc.",
    "UFPT": "Ufp Technologies Inc.", "UGI": "Ugi Corp.", "UHAL": "U Haul Holding",
    "UHALB": "U Haul Non Voting Series N", "UHS": "Universal Health Services", "UHT": "Universal Health Realty Income Tru",
    "UI": "Ubiquiti Inc.", "UIS": "Unisys Corp.", "ULCC": "Frontier Group Holdings Inc.",
    "ULH": "Universal Logistics Holdings Inc.", "ULTA": "Ulta Beauty", "UMBF": "Umb Financial Corp.",
    "UMH": "Umh Properties Inc.", "UNF": "Unifirst Corp.", "UNFI": "United Natural Foods Inc.",
    "UNH": "UnitedHealth Group", "UNIT": "Uniti Group Inc.", "UNM": "Unum",
    "UNP": "Union Pacific Corporation", "UNTY": "Unity Bancorp Inc.", "UPB": "Upstream Bio Inc.",
    "UPBD": "Upbound Group Inc.", "UPS": "United Parcel Service", "UPST": "Upstart Holdings Inc.",
    "UPWK": "Upwork Inc.", "URBN": "Urban Outfitters Inc.", "URGN": "Urogen Pharma LTD",
    "URI": "United Rentals", "USAR": "USA Rare Earth Inc. Class A", "USB": "U.S. Bancorp",
    "USFD": "US Foods Holding Corp.", "USLM": "United States Lime and Minerals IN", "USNA": "Usana Health Sciences Inc.",
    "USPH": "US Physical Therapy Inc.", "UTHR": "United Therapeutics Corp.", "UTI": "Universal Technical Institute Inc.",
    "UTL": "Unitil Corp.", "UTMD": "Utah Medical Products Inc.", "UTZ": "Utz Brands Inc. Class A",
    "UUUU": "Energy Fuels Inc.", "UVE": "Universal Insurance Holdings Inc.", "UVSP": "Univest Financial Corp.",
    "UVV": "Universal Corp.", "UWMC": "Uwm Holdings Corp. Class A", "V": "Visa Inc.",
    "VAC": "Marriott Vacations Worldwide Corp.", "VAL": "Valaris LTD", "VC": "Visteon Corp.",
    "VCEL": "Vericel Corp.", "VCTR": "Victory Capital Holdings Class A I", "VCYT": "Veracyte Inc.",
    "VECO": "Veeco Instruments Inc.", "VEEV": "Veeva Systems Inc. Class A", "VEL": "Velocity Financial Inc.",
    "VERA": "Vera Therapeutics Inc. Class A", "VERX": "Vertex Inc. Class A", "VFC": "VF Corp.",
    "VIAV": "Viavi Solutions Inc.", "VICI": "Vici Properties", "VICR": "Vicor Corp.",
    "VIK": "Viking Holdings LTD", "VIR": "Vir Biotechnology Inc.", "VIRT": "Virtu Financial Inc. Class A",
    "VISN": "Vistance Networks Inc.", "VITL": "Vital Farms Inc.", "VKTX": "Viking Therapeutics Inc.",
    "VLO": "Valero Energy", "VLTO": "Veralto", "VLY": "Valley National",
    "VMC": "Vulcan Materials Company", "VMD": "Viemed Healthcare Inc.", "VMI": "Valmont Inds Inc.",
    "VNDA": "Vanda Pharmaceuticals Inc.", "VNO": "Vornado Realty Trust REIT", "VNOM": "Viper Energy Inc. Class A",
    "VNT": "Vontier Corp.", "VOYA": "Voya Financial Inc.", "VPG": "Vishay Precision Group Inc.",
    "VRDN": "Viridian Therapeutics Ors Inc.", "VRE": "Veris Residential Inc.", "VREX": "Varex Imaging Corp.",
    "VRNS": "Varonis Systems Inc.", "VRRM": "Verra Mobility Corp. Class A", "VRSK": "Verisk Analytics",
    "VRSN": "Verisign", "VRT": "Vertiv Holdings Class A", "VRTS": "Virtus Investment Partners Inc.",
    "VRTX": "Vertex Pharmaceuticals", "VSAT": "Viasat Inc.", "VSCO": "Victoria S Secret",
    "VSEC": "Vse Corp.", "VSH": "Vishay Intertechnology Inc.", "VSNT": "Versant Media Group Inc.",
    "VST": "Vistra Corp.", "VSTS": "Vestis Corp.", "VTOL": "Bristow Group Inc.",
    "VTR": "Ventas", "VTRS": "Viatris", "VTS": "Vitesse Energy Inc.",
    "VVV": "Valvoline Inc.", "VVX": "V2x Inc.", "VYGR": "Voyager Therapeutics Inc.",
    "VYX": "Ncr Voyix Corp.", "VZ": "Verizon", "W": "Wayfair Inc. Class A",
    "WAB": "Wabtec", "WABC": "Westamerica Bancorporation", "WAFD": "Wafd Inc.",
    "WAL": "Western Alliance", "WALD": "Waldencast PLC Class A", "WASH": "Washington Trust Bancorp Inc.",
    "WAT": "Waters Corporation", "WAY": "Waystar Holding Corp.", "WBD": "Warner Bros. Discovery",
    "WBS": "Webster Financial Corp.", "WCC": "Wesco International Inc.", "WD": "Walker & Dunlop Inc.",
    "WDAY": "Workday, Inc.", "WDC": "Western Digital", "WDFC": "Wd-40",
    "WEAV": "Weave Communications Inc.", "WEC": "WEC Energy Group", "WELL": "Welltower",
    "WEN": "Wendys", "WERN": "Werner Enterprises Inc.", "WEST": "Westrock Coffee",
    "WEX": "Wex Inc.", "WFC": "Wells Fargo", "WFRD": "Weatherford International PLC",
    "WGO": "Winnebago Industries Inc.", "WGS": "Genedx Holdings Corp. Class A", "WH": "Wyndham Hotels Resorts Inc.",
    "WHD": "Cactus Inc. Class A", "WHR": "Whirlpool Corp.", "WINA": "Winmark Corp.",
    "WING": "Wingstop Inc.", "WK": "Workiva Inc. Class A", "WKC": "World Kinect Corp.",
    "WLDN": "Willdan Group Inc.", "WLFC": "Willis Lease Finance Corp.", "WLK": "Westlake Corp.",
    "WLY": "John Wiley and Sons Inc. Class A", "WM": "Waste Management", "WMB": "Williams Companies",
    "WMK": "Weis Markets Inc.", "WMS": "Advanced Drainage Systems Inc.", "WMT": "Walmart",
    "WNC": "Wabash National Corp.", "WOOF": "Petco Health and Wellness Company", "WOR": "Worthington Enterprises Inc.",
    "WPC": "W P Carey REIT Inc.", "WRB": "W. R. Berkley Corporation", "WRBY": "Warby Parker Inc. Class A",
    "WRLD": "World Acceptance Corp.", "WS": "Worthington Steel Inc.", "WSBC": "Wesbanco Inc.",
    "WSBF": "Waterstone Financial Inc.", "WSC": "Willscot Holdings Corp. Class A", "WSFS": "Wsfs Financial Corp.",
    "WSM": "Williams-Sonoma, Inc.", "WSO": "Watsco Inc.", "WSR": "Whitestone REIT",
    "WST": "West Pharmaceutical Services", "WT": "Wisdomtree Inc.", "WTBA": "West Bancorporation Inc.",
    "WTFC": "Wintrust Financial Corp.", "WTI": "W and T Offshore Inc.", "WTM": "White Mountains Insurance Group LT",
    "WTRG": "Essential Utilities Inc.", "WTS": "Watts Water Technologies Inc. Class", "WTTR": "Select Water Solutions Inc. Class A",
    "WTW": "Willis Towers Watson", "WU": "Western Union", "WULF": "Terawulf Inc.",
    "WVE": "Wave Life Sciences LTD", "WWD": "Woodward Inc.", "WWW": "Wolverine World Wide Inc.",
    "WY": "Weyerhaeuser", "WYNN": "Wynn Resorts", "XEL": "Xcel Energy",
    "XENE": "Xenon Pharmaceuticals Inc.", "XERS": "Xeris Biopharma Holdings Inc.", "XHR": "Xenia Hotels Resorts REIT Inc.",
    "XMTR": "Xometry Inc. Class A", "XNCR": "Xencor Inc.", "XOM": "ExxonMobil",
    "XP": "XP Class A Inc.", "XPEL": "Xpel Inc.", "XPER": "Xperi Inc.",
    "XPO": "Xpo Inc.", "XPOF": "Xponential Fitness Inc. Class A", "XPRO": "Expro Group Holdings NV",
    "XRAY": "Dentsply Sirona Inc.", "XRN": "Chiron Real Estate Inc.", "XRX": "Xerox Holdings Corp.",
    "XYL": "Xylem Inc.", "XYZ": "Block, Inc.", "YELP": "Yelp Inc.",
    "YETI": "Yeti Holdings Inc.", "YEXT": "Yext Inc.", "YORW": "York Water",
    "YOU": "Clear Secure Inc. Class A", "YUM": "Yum! Brands", "Z": "Zillow Group Inc. Class C",
    "ZBH": "Zimmer Biomet", "ZBIO": "Zenas Biopharma Inc.", "ZBRA": "Zebra Technologies",
    "ZD": "Ziff Davis Inc.", "ZETA": "Zeta Global Holdings Corp. Class A", "ZG": "Zillow Group Inc. Class A",
    "ZION": "Zions Bancorporation", "ZIP": "Ziprecruiter Inc. Class A", "ZM": "Zoom Communications Inc. Class A",
    "ZS": "Zscaler Inc.", "ZTS": "Zoetis", "ZUMZ": "Zumiez Inc.",
    "ZVRA": "Zevra Therapeutics Inc.", "ZWS": "Zurn Elkay Water Solutions Corp.", "ZYME": "Zymeworks Inc.",
}


# ============================================================
# SCORING UTILITY (matches frontend logic)
# ============================================================
def calculateOverallScore(score: dict) -> float:
    if not score:
        return 0
    return (score.get('proximity', 0) * 0.25 + score.get('recency', 0) * 0.20 +
            score.get('relevance', 0) * 0.30 + score.get('uniqueness', 0) * 0.25)


# ============================================================
# WEB SEARCH — DuckDuckGo for grounded expert discovery & verification
# ============================================================

import asyncio
import urllib.parse

DDG_URL = "https://html.duckduckgo.com/html/"
DDG_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ExpertMap/1.0)"}


async def ddg_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo and return text snippets."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                DDG_URL, params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
        if resp.status_code != 200:
            return ""
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|span|td)', resp.text, re.DOTALL
        )
        results = []
        for s in snippets[:max_results]:
            clean = re.sub(r'<[^>]+>', '', s).strip()
            for esc, char in [('&amp;', '&'), ('&#x27;', "'"), ('&quot;', '"'), ('&lt;', '<'), ('&gt;', '>')]:
                clean = clean.replace(esc, char)
            results.append(clean[:300])
        return "\n".join(results)
    except Exception as e:
        print(f"[DDG] Search error for '{query[:50]}': {e}")
        return ""


async def web_search_experts(company_name: str, ticker: str, ecosystem: dict,
                              existing_names: list[str] = None) -> str:
    """Search the web for real people in a company's ecosystem using DuckDuckGo."""
    queries = [
        f'"{company_name}" former VP SVP Director executive LinkedIn',
        f'"{company_name}" former employees senior leadership',
    ]
    competitors = ecosystem.get("competitors", [])[:3]
    for comp in competitors:
        queries.append(f'"{comp}" VP SVP Director leadership team')
    suppliers = ecosystem.get("suppliers", [])[:2]
    for sup in suppliers:
        queries.append(f'"{sup}" VP Director executive team')

    # Run searches in parallel
    tasks = [ddg_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    context_parts = []
    for q, r in zip(queries, results):
        if isinstance(r, str) and r.strip():
            context_parts.append(f"Search: {q}\n{r}")

    context = "\n\n".join(context_parts)
    if context:
        print(f"[SEARCH] Web search returned {len(context)} chars from {len(context_parts)} queries")
    else:
        print("[SEARCH] No web results found")
    return context


async def verify_and_correct_experts(experts: list, company_name: str, ticker: str) -> list:
    """Batch verification: single Gemini Flash call to verify all experts at once,
    then Claude Sonnet reconciles. Much faster than individual calls."""
    if not experts:
        return experts

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Step 1: BATCH verify all experts in ONE Gemini Flash call (instead of 10 individual calls)
    expert_list_text = "\n".join(
        f"{i+1}. {e.get('name','')} | Role: {e.get('currentRole','')} | Company: {e.get('companyAffiliation','')}"
        for i, e in enumerate(experts)
    )
    gemini_evidence = {}
    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=3000,
            messages=[{"role": "user", "content":
                f"Verify each person below. For EACH, on one line, state:\n"
                f"- Their number\n"
                f"- CONFIRMED if correct, WRONG COMPANY if they work elsewhere (state where), or UNKNOWN if you can't verify them\n"
                f"- Their actual company and title if different\n\n"
                f"{expert_list_text}\n\n"
                f"Format: '1. CONFIRMED' or '2. WRONG COMPANY: actually at XYZ Corp as VP Sales' or '3. UNKNOWN'\n"
                f"One line per person. Be specific about company names."}]
        )
        batch_result = msg.content[0].text.strip()
        print(f"[VERIFY-BATCH] Gemini batch result ({len(batch_result)} chars)")
        # Parse batch results — match each line to an expert
        for line in batch_result.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Try to match expert by number or name
            for i, e in enumerate(experts):
                name = e.get('name', '')
                if line.startswith(f"{i+1}.") or line.startswith(f"{i+1})") or name.lower() in line.lower():
                    gemini_evidence[name] = line
                    print(f"[VERIFY-BATCH] {name}: {line[:120]}")
                    break
    except Exception as e:
        print(f"[VERIFY-BATCH] Gemini batch failed: {e}")

    # Step 2: Build evidence report and let Claude Sonnet make final decisions
    expert_json = json.dumps(experts, indent=2)

    evidence_parts = []
    for i, e in enumerate(experts):
        name = e.get('name', '')
        parts = [f"Expert {i+1}: {name}"]
        parts.append(f"  Claimed: {e.get('currentRole','')} at {e.get('companyAffiliation','')}")
        if name in gemini_evidence:
            parts.append(f"  Gemini verification: {gemini_evidence[name]}")
        else:
            parts.append(f"  Gemini verification: (no result — treat as unverified)")
        evidence_parts.append("\n".join(parts))

    evidence_text = "\n\n".join(evidence_parts)
    print(f"[VERIFY] Built evidence report ({len(evidence_text)} chars)")

    correction_prompt = f"""You are reviewing an expert list for accuracy. For each expert, I have verification from Gemini (an independent AI) and optional web search results.

RULES (in priority order):
1. WRONG COMPANY is the #1 disqualifier. If Gemini says "WRONG COMPANY" or indicates the person works at a different company than listed, you MUST either:
   a. CORRECT the companyAffiliation, currentRole, ecosystemNode, and connectionToCompany to reflect their ACTUAL company, OR
   b. REMOVE them (set remove=true) if the corrected company is irrelevant to the research context.
2. If Gemini says someone is CEO, CFO, COO, or CTO of a publicly traded company, REMOVE them (set remove=true).
3. If Gemini says "UNKNOWN PERSON" with no web evidence, REMOVE them (set remove=true) — we need verifiable experts.
4. If Gemini confirms the person at the correct company, keep them as-is.
5. If web evidence and Gemini disagree, prefer the more specific/recent information.
6. companyAffiliation MUST match where they ACTUALLY work. This is critical — an expert listed under the wrong company destroys user trust.
7. If a person's actual company is different but still relevant (e.g., competitor, supplier, customer of the target), CORRECT the entry. If irrelevant, REMOVE.

=== EXPERT LIST ===
{expert_json}
=== END LIST ===

=== VERIFICATION EVIDENCE ===
{evidence_text}
=== END EVIDENCE ===

Return a JSON array. For each expert:
- Keep all original fields
- Update currentRole/companyAffiliation if evidence shows different
- Set "remove": true for C-suite at public companies or clearly wrong people
- Add "verificationNote" with brief explanation
- NEVER include annotations like "(approx.)", "(unverified)", "(estimated)", or "(private)" in ANY field. All data must be clean text.
- companyAffiliation must be the EXACT real company name — no tickers, no annotations, no guesses.

Return ONLY valid JSON array."""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=8192,
            system="You output ONLY valid JSON arrays. No preamble, no commentary, no markdown. Start with [ end with ].",
            messages=[{"role": "user", "content": correction_prompt}]
        )
        raw = msg.content[0].text
        corrected = _extract_json(raw)
        if isinstance(corrected, dict) and "experts" in corrected:
            corrected = corrected["experts"]
        if not isinstance(corrected, list):
            print(f"[VERIFY] Correction returned non-list, keeping originals")
            return experts

        result = []
        for e in corrected:
            if e.get("remove"):
                print(f"[VERIFY] Removed: {e.get('name')} — {e.get('verificationNote', 'no reason')}")
                continue
            e.pop("remove", None)
            result.append(e)

        print(f"[VERIFY] Result: {len(result)} experts after verification (started with {len(experts)})")
        final = sanitize_experts(result if result else experts)
        return final

    except Exception as e:
        print(f"[VERIFY] Correction failed: {e}, keeping originals")
        return sanitize_experts(experts)


# ============================================================
# EXPERT DATA SANITIZATION — strip annotations from all fields
# ============================================================
_ANNOTATION_RE = re.compile(r'\s*\((approx\.?|unverified|estimated|private|public|circa|est\.?|approx|approximate)\)', re.IGNORECASE)

def sanitize_expert(expert: dict) -> dict:
    """Strip annotations like (approx.), (unverified), (private) from expert fields.
    Also clean up company affiliation and current role."""
    for field in ['name', 'currentRole', 'formerRole', 'companyAffiliation', 'connectionToCompany']:
        val = expert.get(field, '')
        if isinstance(val, str):
            # Remove known annotations
            val = _ANNOTATION_RE.sub('', val)
            # Remove trailing commas/periods/whitespace
            val = val.strip().rstrip(',.').strip()
            expert[field] = val
    return expert

def sanitize_experts(experts: list) -> list:
    """Sanitize a list of expert dicts."""
    return [sanitize_expert(e) for e in experts]


# ============================================================
# JSON EXTRACTION
# ============================================================

def _extract_json(text: str):
    """Robustly extract JSON from LLM response.
    Handles: raw JSON, markdown code blocks (```json ... ```),
    JSON embedded in prose, and multiple code blocks."""
    text = text.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code blocks (```json ... ``` or ``` ... ```)
    code_block_pattern = re.compile(r'```(?:json)?\s*\n(.*?)\n\s*```', re.DOTALL)
    matches = code_block_pattern.findall(text)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # Strategy 3: Find the first [ ... ] or { ... } in the text (greedy)
    # Try array first (expert lists), then object
    for start_char, end_char in [('[', ']'), ('{', '}')]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        # Find the matching closing bracket by counting depth
        depth = 0
        for i in range(start_idx, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
            if depth == 0:
                candidate = text[start_idx:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    break

    # Strategy 4: Try removing common LLM prefixes/suffixes
    for prefix in ['Here is', 'Here are', 'Below is', 'The JSON', 'Output:']:
        idx = text.lower().find(prefix.lower())
        if idx >= 0:
            remainder = text[idx + len(prefix):].strip().lstrip(':').strip()
            try:
                return json.loads(remainder)
            except json.JSONDecodeError:
                pass

    raise json.JSONDecodeError("Could not extract JSON from LLM response", text[:200], 0)


# ============================================================
# LLM — Company Profile Generation
# ============================================================

async def generate_company_profile(ticker: str, company_name: Optional[str] = None) -> dict:
    """Generate a full company ecosystem profile via Claude (async, fast model)."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Step 1: ALWAYS use web search to verify the correct company for this ticker
    # Even if company_name was passed as a hint, verify it against web results
    ticker_search = await ddg_search(f'{ticker} stock ticker NYSE NASDAQ company', max_results=5)
    if ticker_search:
        print(f"[COMPANY] DDG ticker lookup for {ticker}: {ticker_search[:200]}")
        try:
            hint_note = f" (Note: the search dropdown suggested '{company_name}' but verify this against the web results.)" if company_name else ""
            id_msg = await client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=200,
                system="You output ONLY the company name, nothing else. No quotes, no explanation.",
                messages=[{"role": "user", "content": f"Based on these web search results, what is the publicly traded company with stock ticker '{ticker}' on NYSE or NASDAQ?{hint_note}\n\n{ticker_search}\n\nReturn ONLY the full company name."}]
            )
            verified_name = id_msg.content[0].text.strip().strip('"').strip("'")
            if verified_name:
                if company_name and verified_name.lower() != company_name.lower():
                    print(f"[COMPANY] Web verification CORRECTED {ticker}: '{company_name}' -> '{verified_name}'")
                company_name = verified_name
            print(f"[COMPANY] Identified {ticker} as: {company_name}")
        except Exception as e:
            print(f"[COMPANY] Ticker identification failed: {e}")

    hint = f" ({company_name})" if company_name else ""

    # Step 2: Search web for company ecosystem information
    ecosystem_search = ""
    search_name = company_name or ticker
    eco_queries = [
        f'{search_name} competitors market',
        f'{search_name} major suppliers customers distributors partners',
        f'{search_name} supply chain key accounts distribution partners',
    ]
    eco_results = await asyncio.gather(*[ddg_search(q) for q in eco_queries], return_exceptions=True)
    eco_parts = [r for r in eco_results if isinstance(r, str) and r.strip()]
    if eco_parts:
        ecosystem_search = "\n\n".join(eco_parts)
        print(f"[COMPANY] Ecosystem web search: {len(ecosystem_search)} chars")

    prompt = f"""Generate a company ecosystem profile for {ticker}{hint}.

=== WEB RESEARCH CONTEXT ===
{ecosystem_search or '(No web context available.)'}
=== END CONTEXT ===

IMPORTANT: Use the web research context above to ensure accuracy. {ticker} is the stock ticker — identify the correct company. Return ONLY valid JSON:

{{
  "ticker": "{ticker}",
  "name": "Full Company Name",
  "sector": "Sector",
  "subIndustry": "Sub-Industry",
  "businessModelSummary": "2-3 sentence business model summary.",
  "endMarkets": ["Market1", "Market2", "Market3", "Market4", "Market5"],
  "competitors": ["Comp1", "Comp2", "Comp3", "Comp4", "Comp5"],
  "suppliers": ["Sup1", "Sup2", "Sup3", "Sup4", "Sup5"],
  "customers": ["Cust1", "Cust2", "Cust3", "Cust4"],
  "distributors": ["Dist1", "Dist2", "Dist3", "Dist4"],
  "regulators": ["Reg1", "Reg2", "Reg3"],
  "industryBodies": ["Body1", "Body2", "Body3"]
}}

CRITICAL RULES FOR ALL LISTS:
- ALWAYS use SPECIFIC, REAL company names — NEVER generic categories.
- WRONG: "Wholesale Distributors", "Screen Printers", "Cotton Suppliers", "Regional Banks", "Catering Companies"
- RIGHT: "AlphaBroder", "SanMar", "S&S Activewear", "JPMorgan Chase", "LSG Sky Chefs"
- Every entry in competitors, suppliers, customers, and distributors MUST be a real, named company or organization.
- If you're unsure of specific names, use the web research context above or your knowledge of the industry.
- For endMarkets, broad market descriptions are OK (e.g., "Activewear", "Retail Apparel").
- For regulators and industryBodies, organization names are expected (e.g., "SEC", "EPA", "OSHA").
- Be accurate. Use real names from the industry."""

    last_error = None
    for attempt in range(2):
        try:
            msg = await client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=2000,
                                          messages=[{"role": "user", "content": prompt}])
            raw = msg.content[0].text
            print(f"[COMPANY] Attempt {attempt+1}: response length {len(raw)} chars")
            data = _extract_json(raw)
            if "company" in data and isinstance(data["company"], dict):
                data = data["company"]
            if not isinstance(data, dict) or "ticker" not in data:
                raise ValueError(f"Invalid company profile structure")
            # Post-generation validation: fix any generic entries
            data = await _fix_generic_ecosystem_entries(data, client)
            return data
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            last_error = e
            print(f"[COMPANY] Attempt {attempt+1} failed: {e}")
            continue
    raise last_error


async def _fix_generic_ecosystem_entries(profile: dict, client) -> dict:
    """Scan ecosystem lists for generic category names and replace them with specific companies."""
    generic_indicators = [
        'companies', 'firms', 'services', 'providers', 'agencies', 'organizations',
        'institutions', 'networks', 'operators', 'manufacturers', 'distributors',
        'retailers', 'suppliers', 'vendors', 'contractors', 'consultants',
        'banks', 'funds', 'insurers', 'carriers', 'utilities', 'producers',
        'refiners', 'processors', 'dealers', 'brokers', 'lenders', 'startups',
        'players', 'cooperatives', 'chains', 'stores', 'shops', 'outlets',
        'wholesalers', 'importers', 'exporters', 'growers', 'mills'
    ]

    def is_generic(name: str) -> bool:
        words = name.lower().split()
        if any(w in generic_indicators for w in words):
            return True
        # Also catch patterns like "Independent Retailers" or "Online Mattress Brands"
        if len(words) >= 2 and (words[-1].endswith('ers') or words[-1].endswith('ors') or words[-1].endswith('ies')):
            return True
        return False

    company_name = profile.get('name', profile.get('ticker', ''))
    lists_to_check = ['competitors', 'suppliers', 'customers', 'distributors']
    generics_found = {}

    for field in lists_to_check:
        items = profile.get(field, [])
        generic_items = [item for item in items if is_generic(item)]
        if generic_items:
            generics_found[field] = generic_items

    if not generics_found:
        return profile  # All entries are specific — no fixes needed

    # Build a single LLM call to resolve all generic entries at once
    fix_parts = []
    for field, items in generics_found.items():
        fix_parts.append(f"{field}: {', '.join(items)}")
    generic_list = "\n".join(fix_parts)

    print(f"[COMPANY-FIX] Found generic entries in {company_name} profile: {generic_list}")

    fix_prompt = f"""The following ecosystem entries for {company_name} are generic categories instead of specific company names.
Replace EACH generic category with 2-3 specific, real companies that fit that category for {company_name}'s industry.

Generic entries to fix:
{generic_list}

Rules:
- Return specific, real company or organization names only.
- Be accurate to {company_name}'s actual industry and business relationships.
- For example, if {company_name} is a mattress company and "Mattress Retailers" is listed, replace with specific retailers like "Mattress Firm", "Sleep Country Canada", "Ashley HomeStore".
- If {company_name} is an apparel company and "Wholesale Distributors" is listed, replace with "AlphaBroder", "SanMar", "S&S Activewear".

Return JSON object with the same field names, each containing an array of specific company names:
Example: {{"distributors": ["AlphaBroder", "SanMar", "S&S Activewear"], "customers": ["Walmart", "Target", "Amazon"]}}

JSON only, no markdown:"""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=1000,
            messages=[{"role": "user", "content": fix_prompt}]
        )
        fixes = _extract_json(msg.content[0].text.strip())
        if isinstance(fixes, dict):
            for field, new_items in fixes.items():
                if field in profile and isinstance(new_items, list):
                    # Replace generic items with specific ones, keep non-generic items
                    original = profile[field]
                    kept = [item for item in original if not is_generic(item)]
                    profile[field] = kept + [item for item in new_items if isinstance(item, str)]
                    print(f"[COMPANY-FIX] {field}: replaced generics with {new_items}")
    except Exception as e:
        print(f"[COMPANY-FIX] Failed to fix generic entries: {e}")

    return profile


# ============================================================
# LLM — Expert Profile Generation
# ============================================================

async def generate_expert_profiles(ticker: str, company_name: str, ecosystem: dict,
                              search_context: str, existing_names: list[str] = None,
                              count: int = 10) -> list:
    """Generate structured expert profiles from web search context + LLM knowledge."""
    global next_expert_id
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    exclude_block = ""
    if existing_names:
        names_list = "\n".join(f"- {n}" for n in existing_names)
        exclude_block = f"\n\nEXCLUDE these people (already listed):\n{names_list}\nGenerate completely different experts."

    competitors = ", ".join(ecosystem.get("competitors", [])[:5])
    suppliers = ", ".join(ecosystem.get("suppliers", [])[:5])

    system_msg = """You are a senior expert network researcher. You output ONLY valid JSON arrays — no preamble, no commentary, no markdown code blocks, no refusals. You MUST always return a JSON array.

Source people from LinkedIn profiles, SEC proxy filings, press releases, and conference bios.
- NEVER include annotations like "(approx.)", "(unverified)", "(estimated)", or "(private)" in any field. All values must be clean text.
- companyAffiliation must be the EXACT legal/common company name where the person currently works. This is the most important field — getting it wrong is unacceptable.
- If you are not confident a person actually works at a specific company, DO NOT include them. Return fewer experts rather than wrong ones.
- Prefer people with distinctive career histories (specific prior employers, board seats, SEC mentions).
- For 'sourceNote', cite the source: 'LinkedIn profile', 'SEC DEF 14A proxy', 'press release', 'conference bio'.
- We have a separate verification step, so generate your best candidates. Do not refuse or provide commentary."""

    prompt = f"""Build an expert network of {count} people for equity investors researching {company_name} ({ticker}).

=== WEB RESEARCH CONTEXT ===
{search_context or "(No web context available.)"}
=== END CONTEXT ===

RULES:
1. Every expert must be a real, publicly documented individual — verifiable via LinkedIn, SEC filings, or press releases.
2. NO C-Suite (CEO, CFO, COO, CTO, CMO, CIO, CHRO) from publicly traded companies. VP/SVP/EVP/Director/GM/Head-of levels ONLY for public companies. C-level at PRIVATE companies is OK.
3. NO sell-side equity analysts from banks. Independent analysts (Gartner, IDC, Forrester) are OK.
4. Accuracy is the top priority. NEVER assign someone to a company where they don't actually work. If you are unsure which company someone works for, OMIT that person entirely. Do NOT add annotations like "(approx.)" to any field — all data must be clean.
5. Do NOT include any current executives of {company_name} itself — they belong in a separate executives list.
{exclude_block}

TARGET MIX ({count} experts):
- "formerEmployee" (3-4): Former VP/SVP/Director at {company_name} who have moved to other companies.
- "competitor" (2-3): VP/Director at competitors ({competitors}). Private co C-level OK.
- "supplier" (1-2): VP/Director at suppliers ({suppliers}).
- "customer" (1-2): VP/Director at major customers/partners.
- "operator" (0-1): Industry operators with relevant domain expertise.

Return a JSON array of {count} objects with this schema:
{{
  "name": "Full Name",
  "currentRole": "Current Title, Current Company",
  "formerRole": "Former role if applicable, or N/A",
  "companyAffiliation": "Current Company",
  "ecosystemNode": "formerEmployee|competitor|supplier|customer|operator",
  "expertise": ["Area1", "Area2", "Area3", "Area4"],
  "yearsExperience": 18,
  "connectionToCompany": "1-2 sentence factual connection to {company_name}",
  "score": {{"proximity": 4, "recency": 4, "relevance": 5, "uniqueness": 4}},
  "linkedinUrl": "https://linkedin.com/in/slug or empty string",
  "sourceNote": "How identified (e.g. SEC proxy, LinkedIn, press release)"
}}

Scoring: proximity 1-5 (5=worked there), recency 1-5, relevance 1-5, uniqueness 1-5.
Former employees: proximity 5. Competitors: 3-4. Suppliers/customers: 3."""

    last_error = None
    # Use Gemini Flash for fast generation — Sonnet handles verification/reconciliation
    models_to_try = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    for attempt, model in enumerate(models_to_try):
        try:
            msg = await client.messages.create(
                model=model, max_tokens=8192,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text
            print(f"[EXPERTS] Attempt {attempt+1} ({model}): response length {len(raw)} chars")
            experts = _extract_json(raw)
            if isinstance(experts, dict) and "experts" in experts:
                experts = experts["experts"]
            if not isinstance(experts, list):
                raise ValueError(f"Expected list, got {type(experts).__name__}")
            # Filter out any current executives of the company that slipped through
            # Use fuzzy matching: compare last names + first names to catch "James E. Lillie" vs "James Lillie"
            company_execs = executives_cache.get(ticker.upper(), [])
            exec_names_exact = {e.get("name", "").lower().strip() for e in company_execs}
            exec_last_first = set()
            for e in company_execs:
                parts = e.get("name", "").lower().split()
                if len(parts) >= 2:
                    exec_last_first.add((parts[-1], parts[0]))  # (last, first)

            def is_exec_duplicate(expert_name):
                name = expert_name.lower().strip()
                if name in exec_names_exact:
                    return True
                parts = name.split()
                if len(parts) >= 2:
                    # Check if last name + first name match any executive
                    if (parts[-1], parts[0]) in exec_last_first:
                        return True
                return False

            before_count = len(experts)
            experts = [e for e in experts if not is_exec_duplicate(e.get("name", ""))]
            if len(experts) < before_count:
                print(f"[EXPERTS] Filtered {before_count - len(experts)} exec duplicates")
            for e in experts:
                e["id"] = next_expert_id
                next_expert_id += 1
                e.setdefault("linkedinUrl", "")
                e.setdefault("sourceNote", "")
            return sanitize_experts(experts)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            last_error = e
            print(f"[EXPERTS] Attempt {attempt+1} failed: {e}")
            continue
    raise last_error


# ============================================================
# LLM — Dynamic Research Questions per Expert
# ============================================================

async def generate_expert_questions(expert: dict, company_name: str, ticker: str) -> list:
    """Generate tailored research questions based on an expert's unique background."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    prompt = f"""You are helping an equity investor prepare for an expert network call on {company_name} ({ticker}).

Expert: {expert['name']}
Current Role: {expert['currentRole']}
Former Role: {expert.get('formerRole', 'N/A')}
Type: {expert['ecosystemNode']}
Expertise: {', '.join(expert.get('expertise', []))}
Connection: {expert.get('connectionToCompany', '')}

Generate 5 specific research questions tailored to this expert's unique experience. Questions should leverage their specific background and seek non-public insights.

Return ONLY a JSON array of strings. No markdown."""

    last_error = None
    for attempt in range(2):
        try:
            msg = await client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1000,
                                          messages=[{"role": "user", "content": prompt}])
            raw = msg.content[0].text
            result = _extract_json(raw)
            if not isinstance(result, list):
                raise ValueError(f"Expected list of questions, got {type(result).__name__}")
            return result
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            print(f"[QUESTIONS] Attempt {attempt+1} failed: {e}")
            continue
    raise last_error



# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(title="Industry Expert Map API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve static files (for Railway deployment)
from fastapi.responses import FileResponse
import pathlib
STATIC_DIR = pathlib.Path(__file__).parent

@app.get("/")
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/app.js")
async def serve_app_js():
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.get("/api/company/{ticker}")
async def get_company(ticker: str, refresh: bool = False):
    """Return company profile, generating on demand."""
    ticker = ticker.upper().replace("-", ".")
    if not refresh and ticker in company_cache:
        return company_cache[ticker]

    name_hint = WELL_KNOWN_COMPANIES.get(ticker)
    try:
        profile = await generate_company_profile(ticker, name_hint)
        company_cache[ticker] = profile
        WELL_KNOWN_COMPANIES[ticker] = profile["name"]
        return profile
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=f"Failed to generate profile for {ticker}: {str(e)}")


@app.get("/api/experts/{ticker}")
async def get_experts(ticker: str):
    """Return experts, generating via web search + LLM on demand."""
    ticker = ticker.upper().replace("-", ".")

    if ticker in experts_cache and experts_cache[ticker]:
        return experts_cache[ticker]

    # Ensure company profile exists — generate if needed
    if ticker not in company_cache:
        name_hint = WELL_KNOWN_COMPANIES.get(ticker)
        try:
            profile = await generate_company_profile(ticker, name_hint)
            company_cache[ticker] = profile
            WELL_KNOWN_COMPANIES[ticker] = profile["name"]
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=422, detail=str(e))

    company = company_cache[ticker]
    try:
        # Ensure executives are loaded first so we can filter them out of expert results
        if ticker not in executives_cache or not executives_cache.get(ticker):
            print(f"[EXPERTS] Loading executives for {ticker} first (for dedup)...")
            try:
                execs = await generate_executives(ticker, company["name"])
                executives_cache[ticker] = execs
            except Exception:
                pass  # Non-fatal — experts can still load without exec dedup

        print(f"[EXPERTS] Web search for {ticker} ({company['name']})...")
        ctx = await web_search_experts(company["name"], ticker, company)
        print(f"[EXPERTS] Generating profiles for {ticker}...")
        experts = await generate_expert_profiles(ticker, company["name"], company, ctx, count=10)
        print(f"[EXPERTS] {ticker}: {len(experts)} candidates, now verifying...")

        # VERIFICATION PASS: check each expert against web search
        experts = await verify_and_correct_experts(experts, company["name"], ticker)

        experts_cache[ticker] = experts
        print(f"[EXPERTS] {ticker}: {len(experts)} verified experts")
        return experts
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


# ============================================================
# BACKGROUND PREFETCH — runs after company-full returns
# ============================================================
async def prefetch_all(ticker: str, company: dict, executives: list, experts: list):
    """Fire-and-forget: prefetch exec-experts, entity-experts, and questions in background."""
    company_name = company.get("name", ticker)
    sem = asyncio.Semaphore(5)  # increased concurrency for faster prefetch

    # Determine what to prefetch
    entity_lists = []
    for etype in ["competitors", "suppliers", "customers", "distributors"]:
        for name in (company.get(etype) or [])[:4]:
            if isinstance(name, str) and name.strip():
                entity_lists.append((name.strip(), etype.rstrip("s")))
    exec_total = len(executives)
    entity_total = len(entity_lists)
    question_total = min(len(experts), 5)  # prefetch questions for top 5 experts

    prefetch_status[ticker] = {
        "status": "running",
        "exec_done": 0, "exec_total": exec_total,
        "entity_done": 0, "entity_total": entity_total,
        "questions_done": 0, "questions_total": question_total,
    }
    print(f"[PREFETCH] {ticker}: Starting background prefetch — {exec_total} execs, {entity_total} entities, {question_total} question sets")

    # --- Prefetch exec-experts ---
    async def prefetch_exec(ex):
        cache_key = f"{ticker}:{ex['name']}"
        if mem_or_disk(exec_experts_cache, "exec_exp", cache_key):
            prefetch_status[ticker]["exec_done"] += 1
            return
        async with sem:
            try:
                exp = await generate_exec_experts(ex["name"], ex.get("title", ""), company_name, ticker)
                exp = await verify_and_correct_experts(exp, company_name, ticker)
                save_both(exec_experts_cache, "exec_exp", cache_key, exp)
                # Register in experts_cache
                all_exp = experts_cache.get(ticker, [])
                for e in exp:
                    if not any(x["id"] == e["id"] for x in all_exp):
                        all_exp.append(e)
                save_both(experts_cache, "experts", ticker, all_exp)
            except Exception as e:
                print(f"[PREFETCH] exec-experts failed for {ex['name']}: {e}")
            prefetch_status[ticker]["exec_done"] += 1

    # --- Prefetch entity-experts ---
    async def prefetch_entity(entity_name, entity_type):
        cache_key = f"{ticker}:{entity_name}"
        if mem_or_disk(entity_experts_cache, "ent_exp", cache_key):
            prefetch_status[ticker]["entity_done"] += 1
            return
        async with sem:
            try:
                exp = await generate_entity_experts(entity_name, entity_type, company_name, ticker)
                exp = await verify_and_correct_experts(exp, company_name, ticker)
                save_both(entity_experts_cache, "ent_exp", cache_key, exp)
                all_exp = experts_cache.get(ticker, [])
                for e in exp:
                    if not any(x["id"] == e["id"] for x in all_exp):
                        all_exp.append(e)
                save_both(experts_cache, "experts", ticker, all_exp)
            except Exception as e:
                print(f"[PREFETCH] entity-experts failed for {entity_name}: {e}")
            prefetch_status[ticker]["entity_done"] += 1

    # --- Prefetch research questions for top experts ---
    async def prefetch_questions(expert):
        cache_key = f"{ticker}:{expert['id']}"
        if mem_or_disk(questions_cache, "questions", cache_key):
            prefetch_status[ticker]["questions_done"] += 1
            return
        async with sem:
            try:
                q = await generate_expert_questions(expert, company_name, ticker)
                save_both(questions_cache, "questions", cache_key, q)
            except Exception as e:
                print(f"[PREFETCH] questions failed for {expert['name']}: {e}")
            prefetch_status[ticker]["questions_done"] += 1

    # Run all prefetch tasks — execs and entities in parallel, then questions
    tasks = []
    for ex in executives:
        tasks.append(prefetch_exec(ex))
    for ename, etype in entity_lists:
        tasks.append(prefetch_entity(ename, etype))
    # Also include questions for top-scored experts
    def _expert_sort_score(e):
        s = e.get("score", {})
        if isinstance(s, dict):
            return s.get("proximity", 0) + s.get("recency", 0) + s.get("relevance", 0) + s.get("uniqueness", 0)
        return s if isinstance(s, (int, float)) else 0
    sorted_experts = sorted(experts, key=_expert_sort_score, reverse=True)[:question_total]
    for exp in sorted_experts:
        tasks.append(prefetch_questions(exp))

    await asyncio.gather(*tasks, return_exceptions=True)
    prefetch_status[ticker]["status"] = "done"
    total_items = exec_total + entity_total + question_total
    print(f"[PREFETCH] {ticker}: Background prefetch complete — {total_items} items processed")


@app.get("/api/prefetch-status/{ticker}")
async def get_prefetch_status(ticker: str):
    """Return the prefetch progress for a given ticker."""
    ticker = ticker.upper().replace("-", ".")
    status = prefetch_status.get(ticker)
    if not status:
        return {"status": "none"}
    return status


@app.post("/api/company-full/{ticker}")
async def get_company_full(ticker: str, request: Request):
    """Two-phase endpoint: returns company + execs fast, experts load in background.
    Frontend polls /api/experts-status/{ticker} to get experts when ready."""
    ticker = ticker.upper().replace("-", ".")

    # Check if refresh requested (body may be empty for POST)
    refresh = False
    try:
        body = await request.json()
        refresh = body.get("refresh", False)
    except Exception:
        pass

    if refresh:
        print(f"[REFRESH] Force-regenerating {ticker} — clearing all caches")
        # Clear all caches for this ticker
        for cache in [company_cache, experts_cache, executives_cache, questions_cache, entity_experts_cache, exec_experts_cache]:
            keys_to_remove = [k for k in cache if k == ticker or k.startswith(f"{ticker}:")]
            for k in keys_to_remove:
                del cache[k]
        # Also clear disk cache for this ticker
        for prefix in ["company", "experts", "execs", "questions", "ent_exp", "exec_exp"]:
            p = _cache_path(prefix, ticker)
            if p.exists():
                p.unlink()
        # Clear prefetch status
        prefetch_status.pop(ticker, None)

    # Step 1: Check caches first
    cached_company = None if refresh else mem_or_disk(company_cache, "company", ticker)
    cached_execs = None if refresh else mem_or_disk(executives_cache, "execs", ticker)
    cached_experts = None if refresh else mem_or_disk(experts_cache, "experts", ticker)

    company = cached_company
    exec_list = cached_execs

    # Step 2: Generate company profile and executives IN PARALLEL if not cached
    if not cached_company or not cached_execs:
        name_hint = WELL_KNOWN_COMPANIES.get(ticker)

        async def _gen_company():
            if cached_company:
                return cached_company
            try:
                c = await generate_company_profile(ticker, name_hint)
                save_both(company_cache, "company", ticker, c)
                WELL_KNOWN_COMPANIES[ticker] = c["name"]
                return c
            except Exception as e:
                traceback.print_exc()
                raise e

        async def _gen_execs(comp):
            if cached_execs:
                return cached_execs
            try:
                cname = comp["name"] if comp else (name_hint or ticker)
                execs = await generate_executives(ticker, cname)
                save_both(executives_cache, "execs", ticker, execs)
                return execs
            except Exception as e:
                print(f"[FULL] Exec generation failed: {e}")
                return []

        if not cached_company:
            # Must get company first (execs need company name), then execs
            try:
                company = await _gen_company()
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"Failed to generate profile for {ticker}: {str(e)}")
            exec_list = await _gen_execs(company)
        else:
            # Company cached, just generate execs
            company = cached_company
            exec_list = await _gen_execs(company)

    # Step 3: If experts already cached, return everything immediately
    if cached_experts:
        return {
            "company": company,
            "executives": exec_list,
            "experts": cached_experts,
            "experts_loading": False
        }

    # Step 4: Experts not cached — kick off background generation, return what we have now
    async def _bg_expert_gen():
        try:
            ctx = await web_search_experts(company["name"], ticker, company)
            experts = await generate_expert_profiles(ticker, company["name"], company, ctx, count=10)
            experts = await verify_and_correct_experts(experts, company["name"], ticker)
            save_both(experts_cache, "experts", ticker, experts)
            print(f"[BG-EXPERTS] {ticker}: {len(experts)} experts ready")
            # Also kick off deeper prefetch
            try:
                await prefetch_all(ticker, company, exec_list, experts)
            except Exception as e:
                print(f"[PREFETCH] Fatal error for {ticker}: {e}")
        except Exception as e:
            print(f"[BG-EXPERTS] Fatal error for {ticker}: {e}")
            experts_cache[ticker] = []  # Mark as done (empty) so frontend stops polling
    asyncio.get_event_loop().create_task(_bg_expert_gen())

    return {
        "company": company,
        "executives": exec_list,
        "experts": [],
        "experts_loading": True
    }


@app.get("/api/experts-status/{ticker}")
async def get_experts_status(ticker: str):
    """Poll endpoint: returns experts once they're ready."""
    ticker = ticker.upper().replace("-", ".")
    cached = mem_or_disk(experts_cache, "experts", ticker)
    if cached is not None:
        return {"ready": True, "experts": cached}
    return {"ready": False, "experts": []}


@app.post("/api/experts/{ticker}/more")
async def get_more_experts(ticker: str):
    """Generate additional experts, excluding existing ones."""
    ticker = ticker.upper().replace("-", ".")
    if ticker not in company_cache:
        raise HTTPException(status_code=404, detail="Generate initial experts first.")

    company = company_cache[ticker]
    existing = experts_cache.get(ticker, [])
    existing_names = [e["name"] for e in existing]

    try:
        print(f"[MORE] Finding more experts for {ticker} (excluding {len(existing_names)})...")
        ctx = await web_search_experts(company["name"], ticker, company, existing_names)
        new_experts = await generate_expert_profiles(
            ticker, company["name"], company, ctx,
            existing_names=existing_names, count=6
        )
        # Verify new experts
        new_experts = await verify_and_correct_experts(new_experts, company["name"], ticker)
        experts_cache[ticker] = existing + new_experts
        print(f"[MORE] {ticker}: +{len(new_experts)} verified experts (total {len(experts_cache[ticker])})")
        return {"new_experts": new_experts, "total": len(experts_cache[ticker])}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/experts/{ticker}/{expert_id}/questions")
async def get_expert_questions(ticker: str, expert_id: int):
    """Generate tailored research questions for a specific expert."""
    ticker = ticker.upper().replace("-", ".")
    cache_key = f"{ticker}:{expert_id}"

    cached = mem_or_disk(questions_cache, "questions", cache_key)
    if cached:
        return cached

    experts = experts_cache.get(ticker, [])
    expert = next((e for e in experts if e["id"] == expert_id), None)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")

    company_name = company_cache.get(ticker, {}).get("name", ticker)
    try:
        questions = await generate_expert_questions(expert, company_name, ticker)
        save_both(questions_cache, "questions", cache_key, questions)
        return questions
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))



# Cache for LLM ticker lookups to avoid repeated calls
ticker_lookup_cache: dict = {}  # query -> [{ticker, name}]

@app.get("/api/search")
async def search_companies(q: str = Query(..., min_length=1)):
    """Search companies by ticker or name. Falls back to LLM lookup if no local matches."""
    query = q.strip().upper()
    query_lower = q.strip().lower()
    results = []
    seen = set()
    is_short = len(query) <= 4  # Short queries: prioritize ticker matches, limit name matches

    def matches(ticker, name):
        """Check if query matches a ticker or company name."""
        # Exact ticker match always wins
        if query == ticker:
            return True
        # Ticker starts with query
        if ticker.startswith(query):
            return True
        # For longer queries (5+ chars), also match company name substrings
        if not is_short and query_lower in name.lower():
            return True
        # For short queries, only match if name starts with a word matching the query
        if is_short:
            name_words = name.lower().split()
            if any(w.startswith(query_lower) for w in name_words):
                return True
        return False

    # Search cached companies first
    for ticker, company in company_cache.items():
        if matches(ticker, company["name"]):
            results.append({"ticker": ticker, "name": company["name"],
                            "sector": company.get("sector", ""), "cached": True})
            seen.add(ticker)

    # Search well-known tickers
    for ticker, name in WELL_KNOWN_COMPANIES.items():
        if ticker in seen:
            continue
        if matches(ticker, name):
            results.append({"ticker": ticker, "name": name, "sector": "", "cached": False})
            seen.add(ticker)

    # If no results found and query is 2+ chars, use web search + LLM to resolve
    if len(results) == 0 and len(q.strip()) >= 2:
        cache_key = query_lower
        if cache_key in ticker_lookup_cache:
            results = ticker_lookup_cache[cache_key]
        else:
            try:
                from anthropic import AsyncAnthropic
                client = AsyncAnthropic()
                # First, do a web search to ground the ticker lookup
                web_context = await ddg_search(f'{q.strip()} stock ticker NYSE NASDAQ company name', max_results=5)
                print(f"[SEARCH-LLM] Web search for '{q.strip()}': {web_context[:200] if web_context else '(empty)'}")
                msg = await client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=500,
                    messages=[{"role": "user", "content": f"""A financial professional searched "{q.strip()}" looking for a US-listed public stock.

=== WEB SEARCH RESULTS ===
{web_context or '(No web results available.)'}
=== END ===

Using the web search results above for accuracy, return the top 3 most likely NYSE/NASDAQ matches as a JSON array:
[{{"ticker": "SYMBOL", "name": "Full Company Name"}}]
IMPORTANT: If "{q.strip()}" matches a real NYSE/NASDAQ ticker symbol exactly, that company MUST be the first result. Use web search results to verify — do NOT guess. For example, PWR = Quanta Services, APG = APi Group Corp. Return ONLY the JSON array."""}]
                )
                raw = msg.content[0].text
                matches = _extract_json(raw)
                if isinstance(matches, list):
                    for m in matches[:3]:
                        t = m.get("ticker", "").upper()
                        n = m.get("name", "")
                        if t and n and t not in seen:
                            results.append({"ticker": t, "name": n, "sector": "", "cached": False})
                            seen.add(t)
                            WELL_KNOWN_COMPANIES[t] = n
                    ticker_lookup_cache[cache_key] = results
            except Exception as ex:
                print(f"[SEARCH-LLM] Fallback lookup failed: {ex}")

    def sort_key(r):
        return (0 if r["ticker"] == query else 1, 0 if r["cached"] else 1, r["ticker"])

    results.sort(key=sort_key)
    return results[:20]


@app.post("/api/company-by-name")
async def get_company_by_name(request: Request):
    """Generate a company profile for any company by name (for private companies in the ecosystem)."""
    body = await request.json()
    name = body.get("name", "").strip()
    entity_type = body.get("type", "company")
    if not name:
        raise HTTPException(status_code=400, detail="Company name is required")

    # Check if we already have it cached by name
    for ticker, comp in company_cache.items():
        if comp["name"].lower() == name.lower():
            experts = experts_cache.get(ticker, [])
            return {"company": comp, "experts": experts, "cached": True}

    # Generate a slug-ticker for caching (use name-based key)
    slug = re.sub(r'[^A-Za-z0-9]', '', name.upper())[:8] + "_PVT"
    if slug in company_cache:
        experts = experts_cache.get(slug, [])
        return {"company": company_cache[slug], "experts": experts, "cached": True}

    try:
        profile = await generate_company_profile(slug, name)
        profile["ticker"] = slug
        profile["name"] = name  # Preserve original name
        profile["isPrivate"] = True
        company_cache[slug] = profile

        print(f"[PRIVATE] Web search for {name}...")
        ctx = await web_search_experts(name, slug, profile)
        print(f"[PRIVATE] Generating expert profiles for {name}...")
        experts = await generate_expert_profiles(slug, name, profile, ctx, count=8)
        experts_cache[slug] = experts

        return {"company": profile, "experts": experts, "cached": False}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


# ============================================================
# LLM — Executive List Generation
# ============================================================
async def generate_executives(ticker: str, company_name: str) -> list:
    """Generate a list of top 10 executives for a company using web search + LLM."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Web search for current executive leadership using DuckDuckGo
    # Use multiple targeted queries to maximize coverage
    search_queries = [
        f'{company_name} management team leadership executives',
        f'{company_name} CEO CFO COO President executive officers 2025 2026',
        f'{company_name} {ticker} proxy statement executive officers annual report',
    ]
    search_tasks = [ddg_search(q) for q in search_queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    search_context_parts = []
    for q, r in zip(search_queries, search_results):
        if isinstance(r, str) and r.strip():
            search_context_parts.append(f"Search: {q}\n{r}")
    search_context = "\n\n".join(search_context_parts)
    if search_context:
        print(f"[EXECS] Web search returned {len(search_context)} chars for {ticker}")
    else:
        print(f"[EXECS] No web results for {ticker} executives")

    prompt = f"""List the top 10 current executives (C-Suite and SVP/EVP level) of {company_name} ({ticker}).

=== WEB RESEARCH (use this as PRIMARY source — prioritize names found here) ===
{search_context or "(No web context — use SEC filings and press releases.)"}
=== END ===

For each executive, provide their name, EXACT current title, a brief description of their role, and department.

CRITICAL ACCURACY RULES:
- ONLY include executives whose names appear in the web research above, in SEC proxy filings, or on the company's official leadership page.
- Names and titles MUST match what is publicly documented. If the web research names specific people, use those names and titles EXACTLY.
- Do NOT guess, infer, or fabricate any executive names. Every name must be a real person who currently holds that position.
- If you can only confidently identify 5-6 executives from the sources, return 5-6 — do NOT pad the list with guesses.
- Aim for at least 7-8 executives — most public companies have this many C-Suite/SVP/EVP officers.
- NEVER return a name you are not confident about. An accurate list of 6 is better than a list of 10 with fabricated names.

Return ONLY a valid JSON array of objects (no markdown, no commentary):
[{{"name": "Full Name", "title": "Exact Current Title", "description": "1 sentence about their role", "department": "e.g. Executive, Finance, Technology"}}]"""

    json_system = "You output ONLY valid JSON arrays. No preamble, no commentary, no markdown code blocks. Start with [ and end with ]."

    models = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    for attempt, model in enumerate(models):
        try:
            msg = await client.messages.create(
                model=model, max_tokens=3000,
                system=json_system,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text
            print(f"[EXECS] Attempt {attempt+1} ({model}): {len(raw)} chars")
            data = _extract_json(raw)
            if isinstance(data, dict) and "executives" in data:
                data = data["executives"]
            if not isinstance(data, list):
                raise ValueError(f"Expected list, got {type(data).__name__}")
            return data[:10]
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[EXECS] Attempt {attempt+1} ({model}) failed: {e}")
    return []


# ============================================================
# LLM — Exec-Linked Expert Generation
# ============================================================
async def generate_exec_experts(exec_name: str, exec_title: str, company_name: str, ticker: str) -> list:
    """Generate 5 former employees who directly reported to a specific executive."""
    global next_expert_id
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Web search for this executive's former reports using DuckDuckGo
    search_queries = [
        f'"{exec_name}" "{company_name}" former direct reports left',
        f'"{company_name}" former VP Director reported to "{exec_name}"',
    ]
    search_tasks = [ddg_search(q) for q in search_queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    context_parts = []
    for q, r in zip(search_queries, search_results):
        if isinstance(r, str) and r.strip():
            context_parts.append(f"Search: {q}\n{r}")
    search_context = "\n\n".join(context_parts)
    if search_context:
        print(f"[EXEC-EXPERTS] Web search returned {len(search_context)} chars")

    prompt = f"""Find 5 real former employees of {company_name} ({ticker}) who worked closely with or directly reported to {exec_name} ({exec_title}) within the past 5 years.

=== WEB RESEARCH ===
{search_context or "(No web context — use publicly known individuals.)"}
=== END ===

These should be VP/Director/Senior Director-level people who:
- Previously worked at {company_name} in a role that would report to {exec_name}
- Have since left the company
- Are real, publicly known individuals (verifiable via LinkedIn, press, SEC)

Return up to 5 candidates. If the web research above names specific people, use those names and titles EXACTLY. For remaining slots, use your knowledge of publicly known VP/Director-level professionals who previously worked at {company_name}.

CRITICAL ACCURACY RULES:
- companyAffiliation must be the EXACT company where the person CURRENTLY works. Getting this wrong is unacceptable.
- NEVER include annotations like "(approx.)", "(unverified)", or "(estimated)" in any field. All data must be clean text.
- If you are not confident about a person's current company, DO NOT include them. Return fewer than 5 rather than include wrong affiliations.
- We have a separate verification step that will catch errors.

Return ONLY a JSON array of objects:
{{
  "name": "Real Full Name",
  "currentRole": "EXACT Current Title, EXACT Current Company",
  "formerRole": "Former Title at {company_name}",
  "companyAffiliation": "Current Company",
  "ecosystemNode": "formerEmployee",
  "expertise": ["Area1", "Area2", "Area3"],
  "yearsExperience": 15,
  "connectionToCompany": "1-2 sentence connection to {company_name} and {exec_name}",
  "reportedTo": "{exec_name}",
  "score": {{"proximity": 5, "recency": 4, "relevance": 5, "uniqueness": 4}},
  "linkedinUrl": "https://linkedin.com/in/slug or empty string",
  "sourceNote": "How identified"
}}

Only real people. No fictional entries."""

    json_system = """You are an expert network researcher. Output ONLY valid JSON arrays — start with [ end with ]. No commentary, no explanations, no refusals.
Source people from LinkedIn profiles, SEC filings, press releases, and conference bios. NEVER include annotations like "(approx.)" or "(unverified)" in any field — all data must be clean text. companyAffiliation must be accurate — omit a person rather than assign them to the wrong company. Return a JSON array of up to 5 candidates."""

    models = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    for attempt, model in enumerate(models):
        try:
            msg = await client.messages.create(
                model=model, max_tokens=3000,
                system=json_system,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text
            experts = _extract_json(raw)
            if isinstance(experts, dict) and "experts" in experts:
                experts = experts["experts"]
            if not isinstance(experts, list):
                raise ValueError(f"Expected list, got {type(experts).__name__}")
            for e in experts:
                e["id"] = next_expert_id
                next_expert_id += 1
                e.setdefault("linkedinUrl", "")
                e.setdefault("sourceNote", "")
                e.setdefault("currentRole", "")
            return sanitize_experts(experts[:5])
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[EXEC-EXPERTS] Attempt {attempt+1} ({model}) failed: {e}")
    return []


# ============================================================
# Resolve entity names — ticker-like strings get expanded to full company names
# ============================================================
async def resolve_entity_name(name: str) -> str:
    """If the name looks like a stock ticker, resolve it to the full company name.
    E.g. 'FTAI' -> 'FTAI Aviation Ltd', 'APG' -> 'APi Group Corp'.
    Returns original name if not a recognizable ticker."""
    stripped = name.strip()
    upper = stripped.upper()

    # Quick check: is it an exact ticker match in our well-known list?
    if upper in WELL_KNOWN_COMPANIES:
        return WELL_KNOWN_COMPANIES[upper]

    # Also check if it's already cached as a company
    if upper in company_cache:
        return company_cache[upper].get("name", stripped)

    # Heuristic: only try LLM resolution for short all-caps strings (1-5 chars)
    # that look like stock tickers, not normal company names
    if len(stripped) <= 5 and stripped == upper and stripped.isalpha():
        print(f"[RESOLVE] '{stripped}' looks like a ticker but not in well-known list, trying LLM")
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic()
            msg = await client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=100,
                messages=[{"role": "user", "content": f"What is the full company name for the US stock ticker '{stripped}'? Reply with ONLY the company name, nothing else. If unknown, reply UNKNOWN."}]
            )
            result = msg.content[0].text.strip().strip('"').strip("'")
            if result and result.upper() != "UNKNOWN" and len(result) > len(stripped):
                print(f"[RESOLVE] LLM resolved '{stripped}' -> '{result}'")
                return result
        except Exception as e:
            print(f"[RESOLVE] LLM resolution failed for '{stripped}': {e}")

    return stripped


# ============================================================
# LLM — Resolve Generic Category to Specific Companies
# ============================================================
async def resolve_generic_entity(entity_name: str, entity_type: str, parent_company: str, parent_ticker: str) -> list:
    """If entity_name is a generic category (e.g., 'Catering Companies', 'Regional Banks'),
    resolve it to a list of specific real companies in the context of the parent company's industry.
    Returns a list of specific company names, or empty list if entity_name is already specific."""
    # Heuristic: generic categories often contain words like 'companies', 'firms', 'services', 'providers'
    # or are plural descriptors rather than proper company names
    generic_indicators = [
        'companies', 'firms', 'services', 'providers', 'agencies', 'organizations',
        'institutions', 'groups', 'associations', 'networks', 'operators', 'manufacturers',
        'distributors', 'retailers', 'suppliers', 'vendors', 'contractors', 'consultants',
        'banks', 'funds', 'insurers', 'carriers', 'airlines', 'utilities',
        'authorities', 'regulators', 'bureaus', 'departments', 'commissions',
        'independent', 'regional', 'local', 'national', 'global', 'international',
        'third-party', 'specialty', 'boutique', 'mid-size', 'small-cap', 'large-cap',
        'producers', 'refiners', 'processors', 'dealers', 'brokers', 'lenders',
        'startups', 'players', 'entrants', 'incumbents', 'conglomerates',
        'cooperatives', 'unions', 'councils', 'boards', 'exchanges'
    ]
    name_lower = entity_name.lower().strip()
    name_words = name_lower.split()
    is_generic = any(word in name_words for word in generic_indicators)

    # Also check: if it doesn't look like a proper company name
    # A proper company name like "LSG Sky Chefs" or "Gate Gourmet" is specific.
    # "Catering Companies" or "Aviation MRO Providers" is generic.
    if not is_generic:
        words = entity_name.split()
        if len(words) >= 2 and all(w[0].isupper() for w in words):
            # Check if last word is a category word
            if words[-1].lower() in generic_indicators:
                is_generic = True

    # Also detect if the name is NOT found as a known company in WELL_KNOWN_COMPANIES
    # and doesn't look like a proper noun pattern (e.g., contains no numbers, no Inc/Corp/Ltd)
    if not is_generic:
        # Check if it matches any known company name
        is_known = any(entity_name.lower() == v.lower() for v in WELL_KNOWN_COMPANIES.values())
        if not is_known:
            # Check for common company suffixes that indicate a real company
            company_suffixes = ['inc', 'corp', 'ltd', 'llc', 'plc', 'co', 'sa', 'ag', 'gmbh', 'nv', 'se']
            has_suffix = any(name_lower.endswith(f' {s}') or name_lower.endswith(f' {s}.') for s in company_suffixes)
            if not has_suffix:
                # Last resort: check if the name ends in a plural noun (likely a category)
                if name_lower.endswith('ers') or name_lower.endswith('ors') or name_lower.endswith('ies'):
                    is_generic = True

    if not is_generic:
        return []  # Not generic — treat as a specific company name

    print(f"[GENERIC-ENTITY] Detected generic category: '{entity_name}' — resolving to specific companies")

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Use LLM to resolve to specific companies, with web search for context
    search_q = f"{parent_company} {entity_type} {entity_name} specific companies"
    web_context = await ddg_search(search_q)

    resolve_prompt = f"""The entity "{entity_name}" is listed as a {entity_type} category for {parent_company} ({parent_ticker}).
This is a GENERIC category, not a specific company. I need you to identify 3-5 specific, real companies that fall into this category AND are relevant to {parent_company}'s business.

{f'Web context: {web_context}' if web_context else ''}

IMPORTANT:
- These must be REAL companies that actually operate as {entity_type}s in {parent_company}'s specific industry/sector.
- Be industry-specific. For example, if {parent_company} is an airline and the category is "Catering Companies", return AIRLINE catering companies like LSG Sky Chefs, Gate Gourmet, DO & CO — NOT general restaurant catering companies.
- If {parent_company} is a construction company and the category is "Equipment Suppliers", return construction equipment companies like Caterpillar, John Deere — NOT office equipment suppliers.
- The context of {parent_company}'s industry is CRITICAL for accuracy.

Return ONLY a JSON array of company name strings. Example: ["LSG Sky Chefs", "Gate Gourmet", "DO & CO"]
No markdown, no explanation."""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=500,
            messages=[{"role": "user", "content": resolve_prompt}]
        )
        raw = msg.content[0].text.strip()
        companies = _extract_json(raw)
        if isinstance(companies, list) and len(companies) > 0 and all(isinstance(c, str) for c in companies):
            print(f"[GENERIC-ENTITY] Resolved '{entity_name}' -> {companies}")
            return companies[:5]
    except Exception as e:
        print(f"[GENERIC-ENTITY] Resolution failed for '{entity_name}': {e}")

    return []


# ============================================================
# LLM — Entity Expert Generation (for clicking companies in ecosystem lists)
# ============================================================
async def generate_entity_experts(entity_name: str, entity_type: str, parent_company: str, parent_ticker: str) -> list:
    """Generate experts from a specific entity in the ecosystem.
    If entity_name is a generic category, resolves to specific companies first."""
    global next_expert_id

    # Step 1: Check if this is a generic category and resolve to specific companies
    specific_companies = await resolve_generic_entity(entity_name, entity_type, parent_company, parent_ticker)
    if specific_companies:
        # Generate experts from each specific company in parallel
        print(f"[ENTITY-EXPERTS] Generating experts from {len(specific_companies)} specific companies for generic '{entity_name}'")
        all_experts = []
        tasks = [
            _generate_entity_experts_for_company(company, entity_type, parent_company, parent_ticker)
            for company in specific_companies
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for company, result in zip(specific_companies, results):
            if isinstance(result, list):
                all_experts.extend(result)
            elif isinstance(result, Exception):
                print(f"[ENTITY-EXPERTS] Failed for {company}: {result}")
        # Return up to 5 best experts across all companies
        return all_experts[:5]

    # Step 2: Specific company name — generate directly
    return await _generate_entity_experts_for_company(entity_name, entity_type, parent_company, parent_ticker)


async def _generate_entity_experts_for_company(entity_name: str, entity_type: str, parent_company: str, parent_ticker: str) -> list:
    """Generate experts from a specific named company."""
    global next_expert_id
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Determine if entity is likely a private company (not in well-known public tickers)
    is_likely_private = not any(entity_name.lower() == v.lower() for v in WELL_KNOWN_COMPANIES.values())

    # Web search for entity leadership using DuckDuckGo — broader queries for private companies
    search_queries = [
        f'"{entity_name}" leadership team executive VP Director',
        f'"{entity_name}" "{parent_company}" {entity_type}',
    ]
    if is_likely_private:
        search_queries.append(f'"{entity_name}" CEO President COO management team')
    search_tasks = [ddg_search(q) for q in search_queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    context_parts = []
    for q, r in zip(search_queries, search_results):
        if isinstance(r, str) and r.strip():
            context_parts.append(f"Search: {q}\n{r}")
    search_context = "\n\n".join(context_parts)
    if search_context:
        print(f"[ENTITY-SEARCH] Web search returned {len(search_context)} chars for {entity_name}")

    c_suite_rule = "C-Suite (CEO, CFO, COO, etc.) is allowed for private companies." if is_likely_private else "NO C-Suite from public companies (VP/SVP/EVP/Director only). C-level OK for private companies."

    prompt = f"""Generate up to 3 expert profiles of senior individuals at {entity_name} relevant to researching {parent_company} ({parent_ticker}).

Relationship: {entity_name} is a {entity_type} of {parent_company}.

=== WEB CONTEXT ===
{search_context or "(No web context — use your knowledge of this company and industry.)"}
=== END ===

RULES:
- {c_suite_rule}
- Every expert MUST actually work (or have recently worked) at {entity_name} specifically — NOT at a different company in the same industry.
- Do NOT confuse people who work at similar/related companies.
- If the web research names specific people with specific titles, use those EXACTLY.
- Use your knowledge of this company's leadership if web results are sparse — {entity_name} is a well-known company in its industry.
- NEVER include annotations like "(approx.)", "(unverified)", or "(estimated)" in any field.
- companyAffiliation must be "{entity_name}" for every expert.
- You MUST return at least 1 expert. Only return an empty array if {entity_name} truly does not exist as a company.

Return ONLY a JSON array of objects (no markdown):
{{"name": "Real Full Name", "currentRole": "EXACT Title at {entity_name}", "formerRole": "Former role or N/A", "companyAffiliation": "{entity_name}", "ecosystemNode": "{entity_type}", "expertise": ["Area1", "Area2", "Area3"], "yearsExperience": 15, "connectionToCompany": "Connection to {parent_company}", "score": {{"proximity": 3, "recency": 4, "relevance": 4, "uniqueness": 4}}, "linkedinUrl": "", "sourceNote": "How identified"}}"""

    json_system = """You are an expert network researcher. Output ONLY valid JSON arrays — start with [ end with ]. No commentary, no explanations, no refusals.
Source people from LinkedIn profiles, SEC filings, press releases, and conference bios. NEVER include annotations like "(approx.)" or "(unverified)" in any field — all data must be clean text. companyAffiliation must be accurate. You MUST always return at least one expert for any real, named company — an empty array is only acceptable if the company does not exist."""

    models = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    for attempt, model in enumerate(models):
        try:
            msg = await client.messages.create(
                model=model, max_tokens=4096,
                system=json_system,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text
            print(f"[ENTITY-EXPERTS] Attempt {attempt+1} ({model}): {len(raw)} chars")
            experts = _extract_json(raw)
            if isinstance(experts, dict) and "experts" in experts:
                experts = experts["experts"]
            if not isinstance(experts, list):
                raise ValueError(f"Expected list")
            print(f"[ENTITY-EXPERTS] Attempt {attempt+1} ({model}): parsed {len(experts)} experts")
            if len(experts) > 0:
                for e in experts:
                    e["id"] = next_expert_id
                    next_expert_id += 1
                    e.setdefault("linkedinUrl", "")
                    e.setdefault("sourceNote", "")
                return sanitize_experts(experts[:5])
            # Empty list from this model — try next model
            print(f"[ENTITY-EXPERTS] Attempt {attempt+1} ({model}): empty result, trying next model")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ENTITY-EXPERTS] Attempt {attempt+1} ({model}) failed: {e}")
    return []


# ============================================================
# LLM — Directory Experts (different set from Company Research experts)
# ============================================================
async def generate_directory_experts(ticker: str, company_name: str, ecosystem: dict) -> list:
    """Generate a DIFFERENT set of experts for the Expert Directory tab.
    Focuses on industry analysts, policy experts, and academic/consulting experts
    rather than the company insiders generated for Company Research."""
    global next_expert_id
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Get names from the Company Research experts to exclude
    existing = experts_cache.get(ticker, [])
    existing_names = [e["name"] for e in existing]
    exclude_block = ""
    if existing_names:
        names_list = ", ".join(existing_names)
        exclude_block = f"\nEXCLUDE these people (already listed): {names_list}. Generate completely different experts."

    # Web search
    ctx = await web_search_experts(company_name, ticker, ecosystem, existing_names)

    competitors = ", ".join(ecosystem.get("competitors", [])[:5])
    suppliers = ", ".join(ecosystem.get("suppliers", [])[:5])
    customers_list = [c for c in ecosystem.get("customers", [])
                      if not any(g in c.lower() for g in ["consumer", "individual", "member", "family", "traveler", "shopper", "budget"])]
    customers = ", ".join(customers_list[:4])

    prompt = f"""Build an ALTERNATIVE expert network for {company_name} ({ticker}).
{ctx or ""}
{exclude_block}

Mix: operators/consultants (3-4), competitor VP/Directors ({competitors}) (2-3), customer contacts ({customers}) (2-3), supplier contacts ({suppliers}) (1-2).

RULES: Real people only. No public-company C-Suite. No sell-side analysts.

Return ONLY a JSON array of 10 objects:
{{"name": "Full Name", "currentRole": "Title, Company", "formerRole": "Former or N/A", "companyAffiliation": "Company", "ecosystemNode": "formerEmployee|competitor|supplier|customer|operator", "expertise": ["A1","A2","A3"], "yearsExperience": 18, "connectionToCompany": "Connection to {company_name}", "score": {{"proximity": 3, "recency": 4, "relevance": 4, "uniqueness": 5}}, "linkedinUrl": "", "sourceNote": "How identified"}}

No markdown."""

    models = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    for attempt, model in enumerate(models):
        try:
            msg = await client.messages.create(model=model, max_tokens=8192,
                                          messages=[{"role": "user", "content": prompt}])
            raw = msg.content[0].text
            experts = _extract_json(raw)
            if isinstance(experts, dict) and "experts" in experts:
                experts = experts["experts"]
            if not isinstance(experts, list):
                raise ValueError(f"Expected list")
            for e in experts:
                e["id"] = next_expert_id
                next_expert_id += 1
                e.setdefault("linkedinUrl", "")
                e.setdefault("sourceNote", "")
            return experts
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[DIR-EXPERTS] Attempt {attempt+1} ({model}) failed: {e}")
    return []


@app.get("/api/executives/{ticker}")
async def get_executives_endpoint(ticker: str):
    """Return top 10 executives for a company."""
    ticker = ticker.upper().replace("-", ".")
    if ticker in executives_cache and executives_cache[ticker]:
        return executives_cache[ticker]

    company_name = company_cache.get(ticker, {}).get("name") or WELL_KNOWN_COMPANIES.get(ticker, ticker)
    try:
        execs = await generate_executives(ticker, company_name)
        executives_cache[ticker] = execs
        return execs
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/exec-experts/{ticker}")
async def get_exec_experts(ticker: str, request: Request):
    """Return 5 former employees who reported to a specific executive."""
    ticker = ticker.upper().replace("-", ".")
    body = await request.json()
    exec_name = body.get("execName", "").strip()
    exec_title = body.get("execTitle", "").strip()
    if not exec_name:
        raise HTTPException(status_code=400, detail="Executive name is required")

    cache_key = f"{ticker}:{exec_name}"
    cached = mem_or_disk(exec_experts_cache, "exec_exp", cache_key)
    if cached:
        return cached

    company_name = company_cache.get(ticker, {}).get("name", ticker)
    try:
        experts = await generate_exec_experts(exec_name, exec_title, company_name, ticker)
        # Verify against web search
        experts = await verify_and_correct_experts(experts, company_name, ticker)
        save_both(exec_experts_cache, "exec_exp", cache_key, experts)
        # Also register these in experts_cache so bio/questions work
        all_experts = experts_cache.get(ticker, [])
        for e in experts:
            if not any(ex["id"] == e["id"] for ex in all_experts):
                all_experts.append(e)
        save_both(experts_cache, "experts", ticker, all_experts)

        return experts
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/entity-experts")
async def get_entity_experts(request: Request):
    """Generate experts from a specific ecosystem entity (competitor, supplier, etc.)."""
    body = await request.json()
    entity_name = body.get("entityName", "").strip()
    entity_type = body.get("entityType", "company").strip()
    parent_ticker = body.get("parentTicker", "").strip().upper()
    if not entity_name:
        raise HTTPException(status_code=400, detail="Entity name is required")

    # Resolve ticker-like names to full company names
    # e.g. "FTAI" -> "FTAI Aviation Ltd", "APG" -> "APi Group Corp"
    resolved_name = await resolve_entity_name(entity_name)
    if resolved_name != entity_name:
        print(f"[ENTITY] Resolved '{entity_name}' -> '{resolved_name}'")

    cache_key = f"{parent_ticker}:{entity_name}"
    cached = mem_or_disk(entity_experts_cache, "ent_exp", cache_key)
    if cached:
        # Return with resolved name so frontend can display it
        if resolved_name != entity_name:
            return {"experts": cached, "resolvedName": resolved_name}
        return cached

    parent_company = company_cache.get(parent_ticker, {}).get("name", parent_ticker)
    try:
        experts = await generate_entity_experts(resolved_name, entity_type, parent_company, parent_ticker)
        # Verify against web search
        experts = await verify_and_correct_experts(experts, parent_company, parent_ticker)
        save_both(entity_experts_cache, "ent_exp", cache_key, experts)
        # Register in experts_cache for bio/questions
        all_experts = experts_cache.get(parent_ticker, [])
        for e in experts:
            if not any(ex["id"] == e["id"] for ex in all_experts):
                all_experts.append(e)
        save_both(experts_cache, "experts", parent_ticker, all_experts)

        # Return with resolved name so frontend can display it
        if resolved_name != entity_name:
            return {"experts": experts, "resolvedName": resolved_name}
        # If experts came from multiple companies (generic category), always return structured
        affiliations = set(e.get("companyAffiliation", "") for e in experts if e.get("companyAffiliation"))
        if len(affiliations) > 1:
            return {"experts": experts, "resolvedCompanies": list(affiliations)}
        return experts
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


# ============================================================
# Expertise-Topic Expert Discovery
# ============================================================
topic_experts_cache: dict = {}  # "ticker:topic" -> list of experts

@app.post("/api/expertise-experts")
async def get_expertise_experts(request: Request):
    """Find experts with a specific expertise/topic area relevant to a company."""
    global next_expert_id
    body = await request.json()
    topic = body.get("topic", "").strip()
    parent_ticker = body.get("parentTicker", "").strip().upper()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    cache_key = f"{parent_ticker}:{topic}"
    cached = mem_or_disk(topic_experts_cache, "topic_exp", cache_key)
    if cached:
        return cached

    parent_company = company_cache.get(parent_ticker, {}).get("name", parent_ticker)
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    # Web search for experts with this expertise
    search_queries = [
        f'"{topic}" expert VP Director senior {parent_company}',
        f'"{topic}" thought leader consultant specialist',
    ]
    search_tasks = [ddg_search(q) for q in search_queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    context_parts = []
    for q, r in zip(search_queries, search_results):
        if isinstance(r, str) and r.strip():
            context_parts.append(f"Search: {q}\n{r}")
    search_context = "\n\n".join(context_parts)

    # Get existing expert names to avoid duplicates
    existing_names = [e["name"] for e in experts_cache.get(parent_ticker, [])]

    prompt = f"""Generate 5 expert profiles of people with deep expertise in "{topic}" who would provide valuable insights for researching {parent_company} ({parent_ticker}).

=== WEB CONTEXT ===
{search_context or "(No web context — use publicly known individuals.)"}
=== END ===

RULES:
- Real verifiable individuals ONLY — use names from LinkedIn, conference speakers, published researchers, or industry consultants.
- Focus on people who are experts in "{topic}" specifically.
- Mix of: former employees, competitors' staff, consultants, industry analysts, or academics who specialize in {topic}.
- NO C-Suite from public companies (VP/SVP/Director only for public cos). C-level OK for private companies.
- NO sell-side analysts from banks.
- Exclude these people (already known): {', '.join(existing_names[:20]) if existing_names else 'None'}

Return ONLY a JSON array (no markdown):
[{{"name": "Real Full Name", "currentRole": "EXACT Title at Company", "formerRole": "Former role or N/A", "companyAffiliation": "Current Company", "ecosystemNode": "industry_expert", "expertise": ["{topic}", "Area2", "Area3"], "yearsExperience": 15, "connectionToCompany": "How their {topic} expertise connects to {parent_company}", "score": {{"proximity": 3, "recency": 4, "relevance": 5, "uniqueness": 4}}, "linkedinUrl": "", "sourceNote": "How identified"}}]"""

    json_system = """You are an expert network researcher. Output ONLY valid JSON arrays — start with [ end with ]. No commentary, no explanations, no refusals.
Source people from LinkedIn profiles, conference bios, published work, and industry directories. NEVER include annotations like "(approx.)" or "(unverified)" in any field — all data must be clean text. companyAffiliation must be accurate — omit a person rather than guess their company."""

    models = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    experts = None
    for attempt, model in enumerate(models):
        try:
            msg = await client.messages.create(
                model=model, max_tokens=4096,
                system=json_system,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text
            experts = _extract_json(raw)
            if isinstance(experts, dict) and "experts" in experts:
                experts = experts["experts"]
            if not isinstance(experts, list):
                raise ValueError("Expected list")
            for e in experts:
                e["id"] = next_expert_id
                next_expert_id += 1
                e.setdefault("linkedinUrl", "")
                e.setdefault("sourceNote", "")
            experts = experts[:5]
            break
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[EXPERTISE-EXPERTS] Attempt {attempt+1} ({model}) failed: {e}")
            continue

    if experts is None:
        experts = []

    if experts:
        # Verify
        experts = await verify_and_correct_experts(experts, parent_company, parent_ticker)
    save_both(topic_experts_cache, "topic_exp", cache_key, experts)

    try:
        # Register in experts_cache for bio/questions
        all_experts = experts_cache.get(parent_ticker, [])
        for e in experts:
            if not any(ex["id"] == e["id"] for ex in all_experts):
                all_experts.append(e)
        save_both(experts_cache, "experts", parent_ticker, all_experts)

        return experts
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/directory-experts/{ticker}")
async def get_directory_experts(ticker: str):
    """Generate a DIFFERENT set of experts for the Expert Directory tab."""
    ticker = ticker.upper().replace("-", ".")

    cached = mem_or_disk(directory_experts_cache, "dir_exp", ticker)
    if cached:
        return cached

    if ticker not in company_cache:
        raise HTTPException(status_code=404, detail="Search company in Company Research first.")

    company = company_cache[ticker]
    try:
        print(f"[DIRECTORY] Generating directory experts for {ticker}...")
        experts = await generate_directory_experts(ticker, company["name"], company)
        save_both(directory_experts_cache, "dir_exp", ticker, experts)
        # Also register in experts_cache for bio/questions
        all_experts = experts_cache.get(ticker, [])
        for e in experts:
            if not any(ex["id"] == e["id"] for ex in all_experts):
                all_experts.append(e)
        save_both(experts_cache, "experts", ticker, all_experts)
        print(f"[DIRECTORY] {ticker}: {len(experts)} directory experts generated")
        return experts
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


# ============================================================
# Relationship Map — expand any company node
# ============================================================
node_ecosystem_cache: dict = {}  # "company_name" -> ecosystem dict


async def generate_node_ecosystem(company_name: str) -> dict:
    """Generate a lightweight ecosystem (competitors, suppliers, customers) for any company."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    prompt = f"""Generate the business ecosystem for {company_name}.

Return ONLY valid JSON:
{{
  "name": "{company_name}",
  "competitors": ["Comp1", "Comp2", "Comp3", "Comp4", "Comp5"],
  "suppliers": ["Sup1", "Sup2", "Sup3"],
  "customers": ["Cust1", "Cust2", "Cust3"]
}}

Use real, accurate company names. Be specific."""

    models = ["claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001"]
    for attempt, model in enumerate(models):
        try:
            msg = await client.messages.create(
                model=model, max_tokens=800,
                system="You output ONLY valid JSON. No preamble, no markdown.",
                messages=[{"role": "user", "content": prompt}]
            )
            data = _extract_json(msg.content[0].text)
            if not isinstance(data, dict):
                raise ValueError("Expected dict")
            data["name"] = company_name
            return data
        except Exception as e:
            print(f"[NODE-ECO] Attempt {attempt+1} ({model}) failed for {company_name}: {e}")
    return {"name": company_name, "competitors": [], "suppliers": [], "customers": []}


@app.post("/api/expand-node")
async def expand_node(request: Request):
    """Expand a company node to get its ecosystem (for relationship map)."""
    body = await request.json()
    company_name = body.get("companyName", "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="Company name is required")

    cache_key = company_name.lower()
    if cache_key in node_ecosystem_cache:
        return node_ecosystem_cache[cache_key]

    # Check if we already have this as a loaded company
    for ticker, comp in company_cache.items():
        if comp["name"].lower() == company_name.lower():
            result = {
                "name": comp["name"],
                "competitors": comp.get("competitors", []),
                "suppliers": comp.get("suppliers", []),
                "customers": comp.get("customers", []),
            }
            node_ecosystem_cache[cache_key] = result
            return result

    try:
        ecosystem = await generate_node_ecosystem(company_name)
        node_ecosystem_cache[cache_key] = ecosystem
        return ecosystem
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(e))


# ============================================================
# EXPERT PUBLICATIONS / ARTICLES
# ============================================================
publications_cache: dict = {}  # "name||affiliation" -> list of publications


async def ddg_search_with_urls(query: str, max_results: int = 8) -> list[dict]:
    """Search DuckDuckGo and return results with titles, URLs, and snippets."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                DDG_URL, params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
        if resp.status_code != 200:
            return []
        # Extract result blocks with URL, title, and snippet
        results = []
        # Find all result links and snippets
        url_matches = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL
        )
        snippet_matches = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|span|td)',
            resp.text, re.DOTALL
        )
        for i, (url, title) in enumerate(url_matches[:max_results]):
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = ''
            if i < len(snippet_matches):
                clean_snippet = re.sub(r'<[^>]+>', '', snippet_matches[i]).strip()
            for esc, char in [('&amp;', '&'), ('&#x27;', "'"), ('&quot;', '"'), ('&lt;', '<'), ('&gt;', '>')]:
                clean_title = clean_title.replace(esc, char)
                clean_snippet = clean_snippet.replace(esc, char)
            # DDG wraps URLs in a redirect — extract the actual URL
            if 'uddg=' in url:
                actual = re.search(r'uddg=([^&]+)', url)
                if actual:
                    url = urllib.parse.unquote(actual.group(1))
            results.append({
                'url': url,
                'title': clean_title[:200],
                'snippet': clean_snippet[:300]
            })
        return results
    except Exception as e:
        print(f"[DDG] URL search error for '{query[:50]}': {e}")
        return []


@app.post("/api/expert-publications")
async def get_expert_publications(request: Request):
    """Find published articles, white papers, blog posts, and conference materials by an expert.
    Uses web search with LLM-powered URL construction fallback."""
    body = await request.json()
    name = body.get("name", "").strip()
    affiliation = body.get("affiliation", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")

    cache_key = f"{name}||{affiliation}"
    if cache_key in publications_cache:
        return publications_cache[cache_key]

    # Try web search first, fall back to LLM-generated references
    first_last = name.split()[0] + ' ' + name.split()[-1] if len(name.split()) > 1 else name
    queries = [
        f'"{first_last}" article OR "white paper" OR blog OR publication',
        f'"{first_last}" conference presentation OR keynote OR interview',
    ]
    if affiliation:
        queries.append(f'"{first_last}" "{affiliation}" insights OR perspective OR wrote')

    # Try web search
    search_tasks = [ddg_search_with_urls(q) for q in queries]
    all_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    combined = []
    seen_urls = set()
    for result_set in all_results:
        if isinstance(result_set, Exception):
            continue
        for r in result_set:
            url_key = r['url'].rstrip('/').lower()
            if url_key not in seen_urls:
                seen_urls.add(url_key)
                combined.append(r)

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()

    if combined:
        # Web search worked — use LLM to filter results
        search_context = json.dumps(combined[:20], indent=2)
        filter_prompt = f"""Given these web search results, identify publications, articles, white papers, blog posts,
conference presentations, interviews, podcasts, or other content that was written by, authored by, or prominently
features insights from "{name}"{f' (affiliated with {affiliation})' if affiliation else ''}.

Search results:
{search_context}

Rules:
1. Only include results where the person is an author, speaker, or primary subject.
2. Exclude LinkedIn profiles, job postings, directories, or people-search sites.
3. Exclude results that merely mention the name in passing.

Return a JSON array (empty array [] if none). Each item:
{{"title": "...", "url": "...", "type": "article|white_paper|blog_post|interview|podcast|conference|report|other", "snippet": "1-sentence description", "source": "Publication name"}}

Return ONLY the JSON array."""
        try:
            msg = await client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=2000,
                messages=[{"role": "user", "content": filter_prompt}]
            )
            publications = _extract_json(msg.content[0].text.strip())
            if not isinstance(publications, list):
                publications = []
            publications_cache[cache_key] = publications[:8]
            return publications_cache[cache_key]
        except Exception as e:
            print(f"[PUBLICATIONS] LLM filter error: {e}")

    # Fallback: Use LLM to identify known publications with Google search links
    pub_prompt = f"""List articles, interviews, white papers, blog posts, conference talks, or podcasts by or prominently featuring {name}{f' ({affiliation})' if affiliation else ''}.

For each, provide a JSON object with:
- title: the title of the piece
- url: a Google search link like https://www.google.com/search?q=ENCODED_QUERY to find it
- type: one of article, white_paper, blog_post, interview, podcast, conference, report
- snippet: one sentence summary
- source: publication name

Rules:
- Only include real, verifiable content. Do not guess or fabricate.
- Use first and last name in the Google search query.
- Return valid JSON array. If you cannot identify any publications with confidence, return exactly: []

Example output format:
[{{"title":"How AI is Transforming Industry","url":"https://www.google.com/search?q=%22John+Smith%22+%22How+AI+is+Transforming+Industry%22","type":"article","snippet":"Smith discusses how AI adoption is reshaping manufacturing.","source":"Harvard Business Review"}}]

JSON array:"""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=2000,
            messages=[{"role": "user", "content": pub_prompt}]
        )
        result_text = msg.content[0].text.strip()
        print(f"[PUBLICATIONS] LLM response for {name}: {result_text[:500]}")
        # Handle empty array directly
        if result_text in ('[]', '[ ]'):
            publications = []
        else:
            try:
                publications = _extract_json(result_text)
            except Exception:
                # Try direct JSON parse
                try:
                    publications = json.loads(result_text)
                except Exception:
                    publications = []
        if not isinstance(publications, list):
            publications = []
        # Validate: ensure each has required fields
        valid = []
        for p in publications[:8]:
            if isinstance(p, dict) and p.get('title') and p.get('url'):
                # Ensure URL is properly formatted
                if not p['url'].startswith('http'):
                    p['url'] = f"https://www.google.com/search?q={urllib.parse.quote(p['title'] + ' ' + name)}"
                valid.append(p)
        publications = valid
    except Exception as e:
        print(f"[PUBLICATIONS] LLM generation error: {e}")
        traceback.print_exc()
        publications = []

    publications_cache[cache_key] = publications
    return publications


@app.get("/api/health")
def health():
    total_experts = sum(len(v) for v in experts_cache.values())
    return {
        "status": "ok",
        "companies_loaded": len(company_cache),
        "experts_total": total_experts,
        "companies_with_experts": len(experts_cache)
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
