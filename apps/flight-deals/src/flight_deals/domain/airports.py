"""Built-in airport / city lookup table and search (FD-2, ADR-0002 FD-2 addendum).

Source of codes: IATA code search (https://www.iata.org/en/publications/directories/
code-search/), cross-checked against Wikipedia (English "List of airports by IATA
airport code" pages for every code; Chinese Wikipedia article infobox IATA field for
airport names). Verified 2026-10-26 by dev-lead; per-entry verification table lives in
``work/tasks/FD-2.md``.

City rows are selectable only when ``city_query_verified`` is True, i.e. a real query
through the price source returned results across several of the city's airports. When an
IATA city code equals the main airport code (e.g. BKK, SIN, LAX, SHA), only the airport
row is kept. Display names are derived at read time and never stored in the database.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal

PlaceKind = Literal["airport", "city"]

MAX_RESULTS = 10
MAX_QUERY_LENGTH = 32


@dataclass(frozen=True)
class Place:
    code: str
    kind: PlaceKind
    city_code: str | None
    zh_name: str
    display_name: str
    en_name: str
    country_zh: str
    aliases: tuple[str, ...] = ()
    city_query_verified: bool = False
    verified_note: str | None = None


def _a(
    code: str,
    zh_name: str,
    display_name: str,
    en_name: str,
    country_zh: str,
    city_code: str | None = None,
    aliases: tuple[str, ...] = (),
) -> Place:
    return Place(code, "airport", city_code, zh_name, display_name, en_name, country_zh, aliases)


def _c(
    code: str,
    zh_name: str,
    en_name: str,
    country_zh: str,
    *,
    verified_note: str | None,
    aliases: tuple[str, ...] = (),
) -> Place:
    return Place(
        code,
        "city",
        None,
        zh_name,
        zh_name,
        en_name,
        country_zh,
        aliases,
        city_query_verified=verified_note is not None,
        verified_note=verified_note,
    )


_FF = "fast-flights 3.1.0, one-way 2026-12-10, max_stops=1"
_GM = "2026-10-26 fast-flights 3.1.0"

# Order matters: within a ranking tier results keep table order (city before its airports).
PLACES: tuple[Place, ...] = (
    # ---- Taiwan ----------------------------------------------------------------------
    _a(
        "TPE",
        "台灣桃園國際機場",
        "台北桃園",
        "Taiwan Taoyuan International Airport",
        "台灣",
        aliases=("台北", "桃園", "Taipei", "Taoyuan"),
    ),
    _a(
        "TSA",
        "台北松山機場",
        "台北松山",
        "Taipei Songshan Airport",
        "台灣",
        aliases=("台北", "松山", "Taipei", "Songshan"),
    ),
    _a(
        "KHH",
        "高雄國際機場",
        "高雄小港",
        "Kaohsiung International Airport",
        "台灣",
        aliases=("小港",),
    ),
    _a(
        "RMQ",
        "台中國際機場",
        "台中清泉崗",
        "Taichung International Airport",
        "台灣",
        aliases=("清泉崗",),
    ),
    _a("TNN", "台南機場", "台南", "Tainan Airport", "台灣"),
    _a("HUN", "花蓮機場", "花蓮", "Hualien Airport", "台灣"),
    _a("MZG", "澎湖機場", "澎湖馬公", "Penghu Airport", "台灣", aliases=("馬公", "Magong")),
    _a("KNH", "金門機場", "金門尚義", "Kinmen Airport", "台灣", aliases=("尚義",)),
    # ---- Japan -----------------------------------------------------------------------
    _c(
        "TYO",
        "東京",
        "Tokyo",
        "日本",
        verified_note=f"{_GM}: TPE->TYO ok, results include HND, NRT (general manager)",
    ),
    _a(
        "NRT",
        "東京成田國際機場",
        "東京成田",
        "Narita International Airport",
        "日本",
        "TYO",
        aliases=("成田", "Narita"),
    ),
    _a(
        "HND",
        "東京羽田國際機場",
        "東京羽田",
        "Haneda Airport",
        "日本",
        "TYO",
        aliases=("羽田", "Haneda"),
    ),
    _c(
        "OSA",
        "大阪",
        "Osaka",
        "日本",
        verified_note=f"{_GM}: TPE->OSA ok, results include ITM, KIX (general manager)",
    ),
    _a(
        "KIX",
        "大阪關西國際機場",
        "大阪關西",
        "Kansai International Airport",
        "日本",
        "OSA",
        aliases=("關西", "Kansai"),
    ),
    _a(
        "ITM",
        "大阪伊丹機場",
        "大阪伊丹",
        "Osaka International Airport",
        "日本",
        "OSA",
        aliases=("伊丹", "Itami"),
    ),
    _a("UKB", "神戶機場", "神戶", "Kobe Airport", "日本", "OSA", aliases=("Kobe",)),
    _c("SPK", "札幌", "Sapporo", "日本", verified_note=None),
    _a(
        "CTS",
        "新千歲機場",
        "札幌新千歲",
        "New Chitose Airport",
        "日本",
        "SPK",
        aliases=("千歲", "北海道", "Chitose"),
    ),
    _a(
        "NGO",
        "中部國際機場",
        "名古屋中部",
        "Chubu Centrair International Airport",
        "日本",
        aliases=("名古屋", "Nagoya", "Centrair"),
    ),
    _a("FUK", "福岡機場", "福岡", "Fukuoka Airport", "日本"),
    _a("OKA", "那霸機場", "沖繩那霸", "Naha Airport", "日本", aliases=("沖繩", "Okinawa")),
    _a("KOJ", "鹿兒島機場", "鹿兒島", "Kagoshima Airport", "日本"),
    _a("KMJ", "熊本機場", "熊本", "Kumamoto Airport", "日本"),
    _a("HIJ", "廣島機場", "廣島", "Hiroshima Airport", "日本"),
    _a("OKJ", "岡山機場", "岡山", "Okayama Airport", "日本"),
    _a("TAK", "高松機場", "高松", "Takamatsu Airport", "日本"),
    _a("MYJ", "松山機場（愛媛）", "愛媛松山", "Matsuyama Airport", "日本", aliases=("愛媛",)),
    _a("SDJ", "仙台機場", "仙台", "Sendai Airport", "日本"),
    _a("KMQ", "小松機場", "小松", "Komatsu Airport", "日本", aliases=("金澤", "Kanazawa")),
    _a("HKD", "函館機場", "函館", "Hakodate Airport", "日本", aliases=("北海道",)),
    _a("AOJ", "青森機場", "青森", "Aomori Airport", "日本"),
    _a("ISG", "新石垣機場", "石垣", "New Ishigaki Airport", "日本", aliases=("石垣", "沖繩")),
    _a(
        "FSZ",
        "富士山靜岡機場",
        "靜岡",
        "Mt. Fuji Shizuoka Airport",
        "日本",
        aliases=("富士山", "Shizuoka"),
    ),
    _a("IBR", "茨城機場", "茨城", "Ibaraki Airport", "日本"),
    _a("HSG", "佐賀機場", "佐賀", "Saga Airport", "日本"),
    # ---- Korea -----------------------------------------------------------------------
    _c(
        "SEL",
        "首爾",
        "Seoul",
        "韓國",
        verified_note=f"2026-10-26 {_FF}: TPE->SEL ok, results include GMP, ICN (dev-lead)",
    ),
    _a(
        "ICN",
        "首爾仁川國際機場",
        "首爾仁川",
        "Incheon International Airport",
        "韓國",
        "SEL",
        aliases=("仁川", "Incheon"),
    ),
    _a(
        "GMP",
        "首爾金浦國際機場",
        "首爾金浦",
        "Gimpo International Airport",
        "韓國",
        "SEL",
        aliases=("金浦", "Gimpo"),
    ),
    _a(
        "PUS",
        "釜山金海國際機場",
        "釜山金海",
        "Gimhae International Airport",
        "韓國",
        aliases=("釜山", "金海", "Busan"),
    ),
    _a("CJU", "濟州國際機場", "濟州", "Jeju International Airport", "韓國", aliases=("濟州島",)),
    _a("TAE", "大邱國際機場", "大邱", "Daegu International Airport", "韓國"),
    _a("CJJ", "清州國際機場", "清州", "Cheongju International Airport", "韓國"),
    # ---- Hong Kong / Macau -----------------------------------------------------------
    _a(
        "HKG",
        "香港國際機場",
        "香港",
        "Hong Kong International Airport",
        "香港",
        aliases=("赤鱲角", "Chek Lap Kok"),
    ),
    _a("MFM", "澳門國際機場", "澳門", "Macau International Airport", "澳門"),
    # ---- China -----------------------------------------------------------------------
    _c(
        "BJS",
        "北京",
        "Beijing",
        "中國",
        verified_note=f"2026-10-26 {_FF}: TPE->BJS ok, results include PEK, PKX (dev-lead)",
    ),
    _a(
        "PEK",
        "北京首都國際機場",
        "北京首都",
        "Beijing Capital International Airport",
        "中國",
        "BJS",
        aliases=("首都",),
    ),
    _a(
        "PKX",
        "北京大興國際機場",
        "北京大興",
        "Beijing Daxing International Airport",
        "中國",
        "BJS",
        aliases=("大興", "Daxing"),
    ),
    _a(
        "SHA",
        "上海虹橋國際機場",
        "上海虹橋",
        "Shanghai Hongqiao International Airport",
        "中國",
        aliases=("虹橋", "Hongqiao"),
    ),
    _a(
        "PVG",
        "上海浦東國際機場",
        "上海浦東",
        "Shanghai Pudong International Airport",
        "中國",
        aliases=("浦東", "Pudong"),
    ),
    _a("CAN", "廣州白雲國際機場", "廣州白雲", "Guangzhou Baiyun International Airport", "中國"),
    _a("SZX", "深圳寶安國際機場", "深圳寶安", "Shenzhen Bao'an International Airport", "中國"),
    _a("CTU", "成都雙流國際機場", "成都雙流", "Chengdu Shuangliu International Airport", "中國"),
    _a("TFU", "成都天府國際機場", "成都天府", "Chengdu Tianfu International Airport", "中國"),
    _a("XMN", "廈門高崎國際機場", "廈門高崎", "Xiamen Gaoqi International Airport", "中國"),
    _a("FOC", "福州長樂國際機場", "福州長樂", "Fuzhou Changle International Airport", "中國"),
    _a("HGH", "杭州蕭山國際機場", "杭州蕭山", "Hangzhou Xiaoshan International Airport", "中國"),
    _a("NKG", "南京祿口國際機場", "南京祿口", "Nanjing Lukou International Airport", "中國"),
    _a("CKG", "重慶江北國際機場", "重慶江北", "Chongqing Jiangbei International Airport", "中國"),
    _a("XIY", "西安咸陽國際機場", "西安咸陽", "Xi'an Xianyang International Airport", "中國"),
    _a("KMG", "昆明長水國際機場", "昆明長水", "Kunming Changshui International Airport", "中國"),
    _a("WUH", "武漢天河國際機場", "武漢天河", "Wuhan Tianhe International Airport", "中國"),
    _a("TAO", "青島膠東國際機場", "青島膠東", "Qingdao Jiaodong International Airport", "中國"),
    _a("CSX", "長沙黃花國際機場", "長沙黃花", "Changsha Huanghua International Airport", "中國"),
    _a("TSN", "天津濱海國際機場", "天津濱海", "Tianjin Binhai International Airport", "中國"),
    _a("DLC", "大連周水子國際機場", "大連", "Dalian Zhoushuizi International Airport", "中國"),
    _a("SYX", "三亞鳳凰國際機場", "三亞鳳凰", "Sanya Phoenix International Airport", "中國"),
    # ---- Southeast Asia ----------------------------------------------------------------
    _a(
        "BKK",
        "曼谷蘇凡納布機場",
        "曼谷蘇凡納布",
        "Suvarnabhumi Airport",
        "泰國",
        aliases=("曼谷", "Bangkok"),
    ),
    _a(
        "DMK",
        "曼谷廊曼國際機場",
        "曼谷廊曼",
        "Don Mueang International Airport",
        "泰國",
        aliases=("曼谷", "Bangkok"),
    ),
    _a("CNX", "清邁國際機場", "清邁", "Chiang Mai International Airport", "泰國"),
    _a(
        "HKT",
        "普吉國際機場",
        "普吉",
        "Phuket International Airport",
        "泰國",
        aliases=("普吉島", "布吉"),
    ),
    _a(
        "SIN",
        "新加坡樟宜機場",
        "新加坡樟宜",
        "Singapore Changi Airport",
        "新加坡",
        aliases=("樟宜", "Changi"),
    ),
    _a("KUL", "吉隆坡國際機場", "吉隆坡", "Kuala Lumpur International Airport", "馬來西亞"),
    _a("PEN", "檳城國際機場", "檳城", "Penang International Airport", "馬來西亞"),
    _a(
        "BKI",
        "亞庇國際機場",
        "亞庇",
        "Kota Kinabalu International Airport",
        "馬來西亞",
        aliases=("沙巴", "Sabah"),
    ),
    _a(
        "MNL",
        "馬尼拉尼諾伊艾奎諾國際機場",
        "馬尼拉",
        "Ninoy Aquino International Airport",
        "菲律賓",
        aliases=("Manila",),
    ),
    _a(
        "CEB",
        "麥克坦宿霧國際機場",
        "宿霧",
        "Mactan-Cebu International Airport",
        "菲律賓",
        aliases=("Cebu",),
    ),
    _a("CRK", "克拉克國際機場", "克拉克", "Clark International Airport", "菲律賓"),
    _a(
        "SGN",
        "胡志明市新山一國際機場",
        "胡志明市",
        "Tan Son Nhat International Airport",
        "越南",
        aliases=("西貢", "Ho Chi Minh City", "Saigon"),
    ),
    _a(
        "HAN",
        "河內內排國際機場",
        "河內",
        "Noi Bai International Airport",
        "越南",
        aliases=("Hanoi",),
    ),
    _a("DAD", "峴港國際機場", "峴港", "Da Nang International Airport", "越南"),
    _a(
        "CXR",
        "芽莊金蘭國際機場",
        "芽莊金蘭",
        "Cam Ranh International Airport",
        "越南",
        aliases=("Nha Trang",),
    ),
    _a(
        "CGK",
        "雅加達蘇加諾-哈達國際機場",
        "雅加達",
        "Soekarno-Hatta International Airport",
        "印尼",
        aliases=("Jakarta",),
    ),
    _a(
        "DPS",
        "峇里島伍拉賴國際機場",
        "峇里島",
        "I Gusti Ngurah Rai International Airport",
        "印尼",
        aliases=("巴里島", "登巴薩", "Bali", "Denpasar"),
    ),
    # ---- Oceania ---------------------------------------------------------------------
    _a(
        "SYD",
        "雪梨金斯福德史密斯機場",
        "雪梨",
        "Sydney Kingsford Smith Airport",
        "澳洲",
        aliases=("悉尼", "Sydney"),
    ),
    _a("MEL", "墨爾本機場", "墨爾本", "Melbourne Airport", "澳洲"),
    _a("BNE", "布里斯本機場", "布里斯本", "Brisbane Airport", "澳洲"),
    _a("AKL", "奧克蘭機場", "奧克蘭", "Auckland Airport", "紐西蘭"),
    _a(
        "GUM",
        "關島國際機場",
        "關島",
        "Antonio B. Won Pat International Airport",
        "美國",
        aliases=("Guam",),
    ),
    # ---- North America -----------------------------------------------------------------
    _c(
        "NYC",
        "紐約",
        "New York",
        "美國",
        verified_note=f"2026-10-26 {_FF}: TPE->NYC ok, results include EWR, JFK, LGA (dev-lead)",
    ),
    _a(
        "JFK",
        "紐約甘迺迪國際機場",
        "紐約甘迺迪",
        "John F. Kennedy International Airport",
        "美國",
        "NYC",
        aliases=("甘迺迪",),
    ),
    _a(
        "EWR",
        "紐華克自由國際機場",
        "紐華克",
        "Newark Liberty International Airport",
        "美國",
        "NYC",
        aliases=("Newark",),
    ),
    _a("LGA", "紐約拉瓜迪亞機場", "紐約拉瓜迪亞", "LaGuardia Airport", "美國", "NYC"),
    _a("LAX", "洛杉磯國際機場", "洛杉磯", "Los Angeles International Airport", "美國"),
    _a("SFO", "舊金山國際機場", "舊金山", "San Francisco International Airport", "美國"),
    _a("SEA", "西雅圖塔科馬國際機場", "西雅圖", "Seattle-Tacoma International Airport", "美國"),
    _a("ONT", "加州安大略國際機場", "加州安大略", "Ontario International Airport", "美國"),
    _a(
        "ORD",
        "芝加哥歐海爾國際機場",
        "芝加哥",
        "O'Hare International Airport",
        "美國",
        aliases=("Chicago",),
    ),
    _a(
        "IAH",
        "休士頓喬治布希洲際機場",
        "休士頓",
        "George Bush Intercontinental Airport",
        "美國",
        aliases=("Houston",),
    ),
    _a("DFW", "達拉斯沃斯堡國際機場", "達拉斯", "Dallas Fort Worth International Airport", "美國"),
    _a(
        "IAD",
        "華盛頓杜勒斯國際機場",
        "華盛頓杜勒斯",
        "Washington Dulles International Airport",
        "美國",
    ),
    _a("BOS", "波士頓羅根國際機場", "波士頓", "Boston Logan International Airport", "美國"),
    _a("PHX", "鳳凰城天港國際機場", "鳳凰城", "Phoenix Sky Harbor International Airport", "美國"),
    _a(
        "HNL",
        "檀香山丹尼爾井上國際機場",
        "檀香山",
        "Daniel K. Inouye International Airport",
        "美國",
        aliases=("夏威夷", "Honolulu", "Hawaii"),
    ),
    _a("YVR", "溫哥華國際機場", "溫哥華", "Vancouver International Airport", "加拿大"),
    _a("YYZ", "多倫多皮爾遜國際機場", "多倫多", "Toronto Pearson International Airport", "加拿大"),
    # ---- Europe / Middle East ------------------------------------------------------------
    _c("LON", "倫敦", "London", "英國", verified_note=None),
    _a(
        "LHR",
        "倫敦希斯洛機場",
        "倫敦希斯洛",
        "Heathrow Airport",
        "英國",
        "LON",
        aliases=("Heathrow",),
    ),
    _a(
        "LGW",
        "倫敦蓋威克機場",
        "倫敦蓋威克",
        "Gatwick Airport",
        "英國",
        "LON",
        aliases=("Gatwick",),
    ),
    _c("PAR", "巴黎", "Paris", "法國", verified_note=None),
    _a("CDG", "巴黎戴高樂機場", "巴黎戴高樂", "Paris Charles de Gaulle Airport", "法國", "PAR"),
    _a("ORY", "巴黎奧利機場", "巴黎奧利", "Paris Orly Airport", "法國", "PAR"),
    _a("AMS", "阿姆斯特丹史基浦機場", "阿姆斯特丹", "Amsterdam Airport Schiphol", "荷蘭"),
    _a("FRA", "法蘭克福機場", "法蘭克福", "Frankfurt Airport", "德國"),
    _a("MUC", "慕尼黑機場", "慕尼黑", "Munich Airport", "德國"),
    _a("VIE", "維也納國際機場", "維也納", "Vienna International Airport", "奧地利"),
    _a("PRG", "布拉格哈維爾國際機場", "布拉格", "Vaclav Havel Airport Prague", "捷克"),
    _a("FCO", "羅馬菲烏米奇諾機場", "羅馬", "Rome Fiumicino Airport", "義大利", aliases=("Rome",)),
    _a("MXP", "米蘭馬爾彭薩機場", "米蘭馬爾彭薩", "Milan Malpensa Airport", "義大利"),
    _a("ZRH", "蘇黎世機場", "蘇黎世", "Zurich Airport", "瑞士"),
    _a("MAD", "馬德里巴拉哈斯機場", "馬德里", "Adolfo Suarez Madrid-Barajas Airport", "西班牙"),
    _a("BCN", "巴塞隆納埃爾普拉特機場", "巴塞隆納", "Barcelona-El Prat Airport", "西班牙"),
    _a("IST", "伊斯坦堡機場", "伊斯坦堡", "Istanbul Airport", "土耳其"),
    _a("DXB", "杜拜國際機場", "杜拜", "Dubai International Airport", "阿拉伯聯合大公國"),
)

_BY_CODE: dict[str, Place] = {p.code: p for p in PLACES}


def normalize(text: str) -> str:
    """NFKC + casefold, and fold the traditional variant 臺 to 台."""
    return unicodedata.normalize("NFKC", text).casefold().replace("臺", "台").strip()


def lookup(code: str) -> Place | None:
    return _BY_CODE.get(code.strip().upper())


def is_selectable(place: Place) -> bool:
    return place.kind == "airport" or place.city_query_verified


def city_group(code: str) -> str:
    """City code a place belongs to (itself for cities and stand-alone airports)."""
    place = lookup(code)
    if place is None:
        return code.strip().upper()
    return place.city_code or place.code


def same_city_group(a: str, b: str) -> bool:
    return city_group(a) == city_group(b)


def city_airports(city_code: str) -> tuple[Place, ...]:
    return tuple(p for p in PLACES if p.city_code == city_code)


def place_label(code: str) -> str:
    """Short display text ``display_name CODE``; codes outside the table fall back to code."""
    place = lookup(code)
    return f"{place.display_name} {place.code}" if place else code


def route_label(origin: str, destination: str) -> str:
    return f"{place_label(origin)} → {place_label(destination)}"


def suggestion_label(place: Place) -> str:
    """Dropdown text: full name, code and country; cities are marked as all airports."""
    if place.kind == "city":
        return f"{place.zh_name}（所有機場）{place.code}（{place.country_zh}）"
    return f"{place.zh_name} {place.code}（{place.country_zh}）"


def _is_cjk(text: str) -> bool:
    return any(ord(ch) > 0x2E7F for ch in text)


def _names(place: Place) -> tuple[list[str], list[str]]:
    """(zh names, en names) searched for a place, including its parent city's names."""
    names = [place.zh_name, place.display_name, *place.aliases, place.en_name]
    if place.city_code:
        parent = _BY_CODE[place.city_code]
        names += [parent.zh_name, *parent.aliases, parent.en_name]
    normalized = [normalize(n) for n in names]
    zh = [n for n in normalized if _is_cjk(n)]
    en = [n for n in normalized if not _is_cjk(n)]
    return zh, en


_SEARCH_INDEX: tuple[tuple[Place, str, list[str], list[str]], ...] = tuple(
    (p, normalize(p.code), *_names(p)) for p in PLACES if is_selectable(p)
)


def _tier(query: str, code: str, zh: list[str], en: list[str]) -> int | None:
    if code == query:
        return 0
    if any(n.startswith(query) for n in zh):
        return 1
    if any(n.startswith(query) for n in en):
        return 2
    if query in code or any(query in n for n in zh + en):
        return 3
    return None


def search_places(q: str, limit: int = MAX_RESULTS) -> list[Place]:
    """Rank: exact code > zh prefix > en prefix > contains; ties keep table order.

    Unverified cities are never returned; their airports still match the city's names.
    """
    query = normalize(q)
    if not query:
        return []
    ranked: list[tuple[int, int, Place]] = []
    for index, (place, code, zh, en) in enumerate(_SEARCH_INDEX):
        tier = _tier(query, code, zh, en)
        if tier is not None:
            ranked.append((tier, index, place))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [place for _, _, place in ranked[: max(0, min(limit, MAX_RESULTS))]]
