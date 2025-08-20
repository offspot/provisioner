NAME = "kiwix-provisioner"  # must be filesystem-friendly (technical)
NAME_CLI = "provisioner"
NAME_HUMAN = "Hotspot Provisioner"

ETH_IFACE: str = "eth0"
WL_IFACE: str = "wlan0"

RC_CANCELED: int = 12
RC_ADVANCED: int = 40
RC_REBOOT: int = 20
RC_HALT: int = 30
RC_UI: int = 50
RC_KILL: int = 128

REGULATORY_DOMAINS: dict[str, str] = {
    "US": "United States",
    "CA": "Canada",
    "JP3": "Japan",
    "DE": "Germany",
    "NL": "Netherlands",
    "IT": "Italy",
    "PT": "Portugal",
    "LU": "Luxembourg",
    "NO": "Norway",
    "FI": "Finland",
    "DK": "Denmark",
    "CH": "Switzerland",
    "CZ": "Czech Republic",
    "ES": "Spain",
    "GB": "United Kingdom",
    "KR": "Republic of Korea (South Korea)",
    "CN": "China",
    "FR": "France",
    "HK": "Hong Kong",
    "SG": "Singapore",
    "TW": "Taiwan",
    "BR": "Brazil",
    "IL": "Israel",
    "SA": "Saudi Arabia",
    "LB": "Lebanon",
    "AE": "United Arab Emirates",
    "ZA": "South Africa",
    "AR": "Argentina",
    "AU": "Australia",
    "AT": "Austria",
    "BO": "Bolivia",
    "CL": "Chile",
    "GR": "Greece",
    "IS": "Iceland",
    "IN": "India",
    "IE": "Ireland",
    "KW": "Kuwait",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "MX": "Mexico",
    "MA": "Morocco",
    "NZ": "New Zealand",
    "PL": "Poland",
    "PR": "Puerto Rico",
    "SK": "Slovak Republic",
    "SI": "Slovenia",
    "TH": "Thailand",
    "UY": "Uruguay",
    "PA": "Panama",
    "RU": "Russia",
    "EG": "Egypt",
    "TT": "Trinidad and Tobago",
    "TR": "Turkey",
    "CR": "Costa Rica",
    "EC": "Ecuador",
    "HN": "Honduras",
    "KE": "Kenya",
    "UA": "Ukraine",
    "VN": "Vietnam",
    "BG": "Bulgaria",
    "CY": "Cyprus",
    "EE": "Estonia",
    "MU": "Mauritius",
    "RO": "Romania",
    "CS": "Serbia and Montenegro",
    "ID": "Indonesia",
    "PE": "Peru",
    "VE": "Venezuela",
    "JM": "Jamaica",
    "BH": "Bahrain",
    "OM": "Oman",
    "JO": "Jordan",
    "BM": "Bermuda",
    "CO": "Colombia",
    "DO": "Dominican Republic",
    "GT": "Guatemala",
    "PH": "Philippines",
    "LK": "Sri Lanka",
    "SV": "El Salvador",
    "TN": "Tunisia",
    "PK": "Islamic Republic of Pakistan",
    "QA": "Qatar",
}

BOOT_ORDER = ["USB_MSD", "NVME", "SD_CARD", "HTTP", "RESTART"]

RTC_CHARGING_VOLTAGE = 3.0

ASCII_LOGO = r"""
 ▄         ▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄▄▄▄▄▄ 
▐░▌       ▐░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌
▐░▌       ▐░▌▐░█▀▀▀▀▀▀▀█░▌ ▀▀▀▀█░█▀▀▀▀ ▐░█▀▀▀▀▀▀▀▀▀ ▐░█▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀█░▌ ▀▀▀▀█░█▀▀▀▀ 
▐░▌       ▐░▌▐░▌       ▐░▌     ▐░▌     ▐░▌          ▐░▌       ▐░▌▐░▌       ▐░▌     ▐░▌     
▐░█▄▄▄▄▄▄▄█░▌▐░▌       ▐░▌     ▐░▌     ▐░█▄▄▄▄▄▄▄▄▄ ▐░█▄▄▄▄▄▄▄█░▌▐░▌       ▐░▌     ▐░▌     
▐░░░░░░░░░░░▌▐░▌       ▐░▌     ▐░▌     ▐░░░░░░░░░░░▌▐░░░░░░░░░░░▌▐░▌       ▐░▌     ▐░▌     
▐░█▀▀▀▀▀▀▀█░▌▐░▌       ▐░▌     ▐░▌      ▀▀▀▀▀▀▀▀▀█░▌▐░█▀▀▀▀▀▀▀▀▀ ▐░▌       ▐░▌     ▐░▌     
▐░▌       ▐░▌▐░▌       ▐░▌     ▐░▌               ▐░▌▐░▌          ▐░▌       ▐░▌     ▐░▌     
▐░▌       ▐░▌▐░█▄▄▄▄▄▄▄█░▌     ▐░▌      ▄▄▄▄▄▄▄▄▄█░▌▐░▌          ▐░█▄▄▄▄▄▄▄█░▌     ▐░▌     
▐░▌       ▐░▌▐░░░░░░░░░░░▌     ▐░▌     ▐░░░░░░░░░░░▌▐░▌          ▐░░░░░░░░░░░▌     ▐░▌     
 ▀         ▀  ▀▀▀▀▀▀▀▀▀▀▀       ▀       ▀▀▀▀▀▀▀▀▀▀▀  ▀            ▀▀▀▀▀▀▀▀▀▀▀       ▀      
""".strip(
    "\n"
)

USB_BUS_SPEED_PER_SECOND = "375MiB"

# in-order list of sound files to play upon provision completion
SUCCESS_SOUNDS = ["notification.wav", "provision_succeeded.wav"]
FAILURE_SOUNDS = ["error.wav", "provision_failed.wav"]
