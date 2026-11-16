"""The client's country (Stanislav 11-16: English-speaking clients are asked «Where are you from?»). clients.profile
stores {"country": {"code": "IL", "name": "Israel"}} (ISO 3166-1 alpha-2 + the English name); the CRM names it in its own
language via Intl.DisplayNames. ponytail: names only in English + a few aliases; free text in another script stays
unmatched (stored as typed, code null)."""
import re

# the questionnaire's buttons: the most common countries of Tbilisi tenants
TOP = ("RU", "UA", "BY", "KZ", "IL", "IN", "IR", "TR", "US", "GB", "DE", "PL")

_ISO = """AF Afghanistan|AL Albania|DZ Algeria|AD Andorra|AO Angola|AG Antigua and Barbuda|AR Argentina|AM Armenia|AU Australia|
AT Austria|AZ Azerbaijan|BS Bahamas|BH Bahrain|BD Bangladesh|BB Barbados|BY Belarus|BE Belgium|BZ Belize|BJ Benin|BT Bhutan|
BO Bolivia|BA Bosnia and Herzegovina|BW Botswana|BR Brazil|BN Brunei|BG Bulgaria|BF Burkina Faso|BI Burundi|KH Cambodia|
CM Cameroon|CA Canada|CV Cape Verde|CF Central African Republic|TD Chad|CL Chile|CN China|CO Colombia|KM Comoros|CG Congo|
CD DR Congo|CR Costa Rica|CI Ivory Coast|HR Croatia|CU Cuba|CY Cyprus|CZ Czechia|DK Denmark|DJ Djibouti|DM Dominica|
DO Dominican Republic|EC Ecuador|EG Egypt|SV El Salvador|GQ Equatorial Guinea|ER Eritrea|EE Estonia|SZ Eswatini|ET Ethiopia|
FJ Fiji|FI Finland|FR France|GA Gabon|GM Gambia|GE Georgia|DE Germany|GH Ghana|GR Greece|GD Grenada|GT Guatemala|GN Guinea|
GW Guinea-Bissau|GY Guyana|HT Haiti|HN Honduras|HK Hong Kong|HU Hungary|IS Iceland|IN India|ID Indonesia|IR Iran|IQ Iraq|
IE Ireland|IL Israel|IT Italy|JM Jamaica|JP Japan|JO Jordan|KZ Kazakhstan|KE Kenya|KI Kiribati|KP North Korea|KR South Korea|
XK Kosovo|KW Kuwait|KG Kyrgyzstan|LA Laos|LV Latvia|LB Lebanon|LS Lesotho|LR Liberia|LY Libya|LI Liechtenstein|LT Lithuania|
LU Luxembourg|MG Madagascar|MW Malawi|MY Malaysia|MV Maldives|ML Mali|MT Malta|MH Marshall Islands|MR Mauritania|
MU Mauritius|MX Mexico|FM Micronesia|MD Moldova|MC Monaco|MN Mongolia|ME Montenegro|MA Morocco|MZ Mozambique|MM Myanmar|
NA Namibia|NR Nauru|NP Nepal|NL Netherlands|NZ New Zealand|NI Nicaragua|NE Niger|NG Nigeria|MK North Macedonia|NO Norway|
OM Oman|PK Pakistan|PW Palau|PS Palestine|PA Panama|PG Papua New Guinea|PY Paraguay|PE Peru|PH Philippines|PL Poland|
PT Portugal|QA Qatar|RO Romania|RU Russia|RW Rwanda|KN Saint Kitts and Nevis|LC Saint Lucia|VC Saint Vincent and the Grenadines|
WS Samoa|SM San Marino|ST Sao Tome and Principe|SA Saudi Arabia|SN Senegal|RS Serbia|SC Seychelles|SL Sierra Leone|
SG Singapore|SK Slovakia|SI Slovenia|SB Solomon Islands|SO Somalia|ZA South Africa|SS South Sudan|ES Spain|LK Sri Lanka|
SD Sudan|SR Suriname|SE Sweden|CH Switzerland|SY Syria|TW Taiwan|TJ Tajikistan|TZ Tanzania|TH Thailand|TL Timor-Leste|TG Togo|
TO Tonga|TT Trinidad and Tobago|TN Tunisia|TR Turkey|TM Turkmenistan|TV Tuvalu|UG Uganda|UA Ukraine|AE United Arab Emirates|
GB United Kingdom|US United States|UY Uruguay|UZ Uzbekistan|VU Vanuatu|VA Vatican|VE Venezuela|VN Vietnam|YE Yemen|ZM Zambia|
ZW Zimbabwe"""
NAMES = dict(x.strip().split(" ", 1) for x in _ISO.split("|"))
_ALIAS = {"usa": "US", "us": "US", "america": "US", "united states of america": "US", "uk": "GB", "england": "GB",
          "britain": "GB", "great britain": "GB", "scotland": "GB", "wales": "GB", "russian federation": "RU", "rf": "RU",
          "uae": "AE", "emirates": "AE", "dubai": "AE", "korea": "KR", "czech republic": "CZ", "holland": "NL",
          "turkiye": "TR", "türkiye": "TR", "persia": "IR", "cote d'ivoire": "CI", "macedonia": "MK", "burma": "MM",
          "россия": "RU", "украина": "UA", "беларусь": "BY", "казахстан": "KZ", "израиль": "IL", "индия": "IN",
          "иран": "IR", "турция": "TR", "сша": "US", "германия": "DE", "армения": "AM", "азербайджан": "AZ"}
_BY_NAME = {**{n.lower(): c for c, n in NAMES.items()}, **_ALIAS}


def flag(code):
    """ISO code -> 🇮🇱 (regional indicator letters)."""
    return "".join(chr(0x1F1E6 + ord(ch) - 65) for ch in code) if code and len(code) == 2 and code.isalpha() else "🌍"


def of(code):
    return {"code": code, "name": NAMES[code]}


def parse(text):
    """A typed country -> {"code", "name"}: an ISO code, an English name or alias; else as typed with code None."""
    t = re.sub(r"\s+", " ", (text or "").strip(" .!\n\t")).lower()
    if not t:
        return None
    if len(t) == 2 and t.upper() in NAMES:
        return of(t.upper())
    code = _BY_NAME.get(t) or _BY_NAME.get(re.sub(r"^the ", "", t))
    return of(code) if code else {"code": None, "name": text.strip()[:60]}


def label(c):
    """{"code": "IL", "name": "Israel"} -> «🇮🇱 Israel»."""
    return c and c.get("name") and f"{flag(c.get('code'))} {c['name']}"


if __name__ == "__main__":
    assert parse("israel") == of("IL") and parse("USA") == of("US") and parse(" the Netherlands ") == of("NL")
    assert parse("de") == of("DE") and parse("Atlantis") == {"code": None, "name": "Atlantis"} and parse("  ") is None
    assert flag("IL") == "🇮🇱" and label(of("IL")) == "🇮🇱 Israel" and all(c in NAMES for c in TOP)
    print("ok")
