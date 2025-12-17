# Define proxies
USE_PROXY = True # Set to True to enable proxy usage
PROXY_FIRST = True
# Proxy Configuration
PROXY_USERNAME = "rcbforever2036"
PROXY_PASSWORD = "gqoagZF2Vt"
PROXY_HOST = "103.235.64.207"
PROXY_PORT = 50100

# http://nx1botz0mqGZ:NnbJos5GRX@103.235.64.209:50100
# http://paypalmafiabots:Aryan@103.172.84.222:50100
# http://nx1botz0zIn6:sVF4DJXFt8@103.167.32.218:49155
# http://paypalmafiabots:TeamUniverse@103.235.64.29:50100
# Format: protocol://username:password@host:port
PROXY_URL = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"

# http://paypalmafiabots:Gdha@103.172.84.29:50100

# Proxy dictionary for requests
PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL
}

MP4_USER_IDS = {"5833114414"}  # User IDs that get mp4 extension instead of mkv

# Whether to keep and dump streams after muxing (True) or delete them immediately (False)
DUMP_STREAMS = False

pickFormats = {
    "audio": {
        'tam': "Tamil", 'tel': "Telugu", 'mal': "Malayalam", 'hin': "Hindi",
        'kan': "Kannada", 'mar': "Marathi", 'ben': "Bengali", 'pun': "Punjabi", 
        'guj': "Gujarati", 'ori': "Odia", 'ass': "Assamese", 'kha': "Kashmiri",
        'sar': "Sanskrit", 'ur': "Urdu", 'ma': "Maithili", 'bho': "Bhojpuri",
        'nep': "Nepali", 'sindhi': "Sindhi", 'santali': "Santali", 'dogri': "Dogri",
        'raj': "Rajasthani", 'eng': "English", 'spa': "Spanish", 'fra': "French",
        'ger': "German", 'chi': "Chinese", 'ja': "Japanese", 'ko': "Korean",
        'en': "English", 'bn': "Bengali", 'gu': "Gujarati", 'kn': "Kannada",
        'mr': "Marathi", 'ml': "Malayalam", 'ta': "Tamil", 'te': "Telugu",
        'hi': "Hindi"
    }
}

def get_language_name(audio_locale):
    """Convert language code to full name"""
    # Add mapping for language codes to full names
    language_map = {'ja-JP': 'Japanese', 'en-US': 'English', 'es-419': 'Spanish', 'pt-BR': 'Portuguese', 'de-DE': 'German', 'hi-IN': 'Hindi', 'fr-FR': 'French', 'it-IT': 'Italian',
        'es-ES': 'Spanish', 'ta-IN': 'Tamil', 'te-IN': 'Telugu', 'ko-KR': 'Korean', 'ru-RU': 'Russian', 'ar-ME': 'Arabic', 'tr-TR': 'Turkish', 'vi-VN': 'Vietnamese',
        'th-TH': 'Thai', 'zh-CN': 'Chinese', 'zh-TW': 'Chinese', 'id-ID': 'Indonesian', 'ms-MY': 'Malay', 'fil-PH': 'Filipino', 'bn-IN': 'Bengali', 'gu-IN': 'Gujarati',
        'kn-IN': 'Kannada', 'ml-IN': 'Malayalam', 'mr-IN': 'Marathi', 'or-IN': 'Odia', 'pa-IN': 'Punjabi', 'as-IN': 'Assamese', 'ks-IN': 'Kashmiri', 'sa-IN': 'Sanskrit',
        'ur-IN': 'Urdu', 'mai-IN': 'Maithili', 'bho-IN': 'Bhojpuri', 'ne-IN': 'Nepali', 'sd-IN': 'Sindhi', 'sat-IN': 'Santali', 'doi-IN': 'Dogri', 'raj-IN': 'Rajasthani',
        'uk-UA': 'Ukrainian', 'pl-PL': 'Polish', 'cs-CZ': 'Czech', 'sk-SK': 'Slovak', 'hu-HU': 'Hungarian', 'ro-RO': 'Romanian', 'bg-BG': 'Bulgarian', 'hr-HR': 'Croatian',
        'sr-RS': 'Serbian', 'sl-SI': 'Slovenian', 'el-GR': 'Greek', 'he-IL': 'Hebrew', 'fa-IR': 'Persian', 'sw-KE': 'Swahili', 'am-ET': 'Amharic', 'ka-GE': 'Georgian',
        'hy-AM': 'Armenian', 'az-AZ': 'Azerbaijani', 'uz-UZ': 'Uzbek', 'tg-TJ': 'Tajik', 'tk-TM': 'Turkmen', 'ky-KG': 'Kyrgyz', 'mn-MN': 'Mongolian', 'my-MM': 'Burmese',
        'km-KH': 'Khmer', 'lo-LA': 'Lao'}
    return language_map.get(audio_locale, audio_locale)

# ISO 639-1 to ISO 639-2 mapping
def get_iso_639_2(lang_code):
    iso_map = {
        'en': 'eng', 'de': 'deu', 'es': 'spa', 'fr': 'fra', 'it': 'ita', 'tr': 'tur',
        'hi': 'hin', 'ta': 'tam', 'te': 'tel', 'kn': 'kan', 'ml': 'mal', 'bn': 'ben',
        'gu': 'guj', 'mr': 'mar', 'pa': 'pan', 'ar': 'ara', 'zh': 'zho', 'ja': 'jpn',
        'ko': 'kor', 'ru': 'rus', 'pt': 'por', 'nl': 'nld', 'pl': 'pol', 'vi': 'vie',
        'id': 'ind', 'th': 'tha', 'sv': 'swe', 'da': 'dan', 'fi': 'fin', 'no': 'nor',
        'cs': 'ces', 'el': 'ell', 'he': 'heb', 'ro': 'ron', 'hu': 'hun', 'uk': 'ukr',
        'ms': 'msa'  # Added Malay language code
    }
    return iso_map.get(lang_code, lang_code)

# OTT ACCOUNTS TOKENS

## AHA (fix)
## DEVICE_ID = "b7786cf5-89de-4414-ae58-0b5c96af07fa"

## AMAZON PRIME
COOKIE = 'session-token="DK5rB3te6AX2faWZTY6Eqazk8E61Fq5bJA5NGZfLhfa8zSZd69HL2q8vBu8dxqU3JGi/TXJOz9sE4ZVU9vs611cussKmVG9URHjsEII/DaRDx/nphFhitmU3AfZrQzH235QYi/NT1zKpEpMVy8ha8tPVJihZCHuox6ZAEH7dQLbfIX13xLh/Xs8Swo04aEolIiQH1Xzf9biVVVsZZUl3Kv9/rGt3QDyd/P2/hrh52bOdXVPUgWy8wYIMGvGZ7URcnjGOCxLR5fePAX6F33poIEcoilUlVAEiIcZg3rYHqysupfsG2uLb9RJD31vmPg65+XHQMR0pSzmsPhfEcvc3Px2i3XOCKxIf3Wps5cCqL/lvwPl3Jmt9q4sugWmkUMHBGNoytFhl+Ec=";csm-hit=tb:XA83Y3P7ZQX2HGZ02VAK+s-5XDRKATNKQZX4HXAZQJA|1738668556732&t:1738668556732&adb:adblk_no;i18n-prefs=USD;x-main-av="2nD7KNLUO1JjdxoBt475D@JvBqVHJziTU9w?MyvQQe4G0phnYy72P@77ertBJS82";sess-at-main-av="G9geAIxwD7SiydFiiQ/Wj/pBqhaS+TNXjxuBlpavWeM=";av-profile=cGlkPWFtem4xLmFjdG9yLnBlcnNvbi5vaWQuQTNPSjJFUTdYMENFSjUmdGltZXN0YW1wPTE3Mzg2Njg1MzU5MjImdmVyc2lvbj12MQ.g2MJ7578s2xtAEBngajnkJCEhyzGo6vhUk6KuImgJugPAAAAAQAAAABnofn3cmF3AAAAAPgWC9WfHH8iB-olH_E9xQ;lc-main-av=tr_TR;at-main-av=Atza|IwEBINrgapgrwJymqA9K_i10Mcl79kGIN0xXA-QRqNv5hlUsSNJC8qJfHF9FaMsQl5rmSU9CxE-fGXsuwnGmQfAKQf8umba4tGtwVf4Gpk3oCWaeb9NtDWKhksk_yw4egbqd1V7-kg79jxiHtCaSvCMr7kow6FQYvUgMoQ9QV51CSKDYb_7I193X3CzEOL22s4O2nqtBVuQLSVhatfKd9ifuWoCkoCHpqeQK3bWuTxbq49G_J8Gg-lC341sWWfeMu_fRspU;session-id-time=2082787201l;session-id=257-8234167-1982110;ubid-main-av=262-4038984-0944217'

## CRUNCHYROLL
COOKIE_CONFIG = 'device_id=c1b89a32-d1fd-4723-860f-75375ce9cb25; c_locale=en-US; device_id=c1b89a32-d1fd-4723-860f-75375ce9cb25; __cf_bm=WhGCGxYvzR3zF0jBuPVgAPd1KjEKlk8zQXovTBeFzso-1753287770-1.0.1.1-M0OAiJHrasmnc.aXyVx6cO1Z9Y0piOVaO7kQOSASA0yoZOKZnJ.8EZ8z4ggUDIMEg5C_vmdEnwPGT_8G0kpaMwgt1dZXbkH1RYfEKYjY4KdIc01ytRiqI2CAtfMdQ7d8; ajs_anonymous_id=e4145913-b45d-41d3-967a-ce0df9965d45; cf_clearance=O7gePey4lp1Q563eOCrZTho.oA0UriXz10cA90vTJ5c-1753287856-1.2.1.1-d_aJn5ppC0Mw3IMvfhGqsOPVKxEWEpCd8eIouJ0H9yhCmK14HiLlZg4yKPrHtgeGiimSDLyegjGi4uKWO7R_YHeeP0veSmLH2LOgnu1mrbjqcmqp6S0_cp3rzFg.4VSJP4lNNm3TGgkU0quQViKrE4HCyEJycSPj55pBBeNL8Yl9cvSW_n2gGKNm9ig4O0wYP8JIuuuFfxYsPXWtpSkg8IZShdItziVkF3unsSTpJDg; etp_rt=331d0d55-75ee-4685-ac85-c1fdf64f1573; ab.storage.userId.80f403d2-1c18-471d-b0ef-243d1d646436=%7B%22g%22%3A%225b5073ab-137d-5af4-b5dc-7b68c5dd64d1%22%2C%22c%22%3A1753287880966%2C%22l%22%3A1753287880967%7D; ab.storage.deviceId.80f403d2-1c18-471d-b0ef-243d1d646436=%7B%22g%22%3A%22dab89d1a-f3c2-b65c-45d0-f0d97da0c797%22%2C%22c%22%3A1753287880968%2C%22l%22%3A1753287880968%7D; ab.storage.sessionId.80f403d2-1c18-471d-b0ef-243d1d646436=%7B%22g%22%3A%2251e170ed-bd5d-bef9-50dd-db78074229d5%22%2C%22e%22%3A1753289680971%2C%22c%22%3A1753287880967%2C%22l%22%3A1753287880971%7D; _dd_s=rum=2&id=556bd2f5-df75-4c6e-acc6-8d1d9abcb6e9&created=1753287776368&expire=1753289079340'

## CHAUPAL TV
API_KEY = "AIzaSyCy9pm1PChZKOULywz9FBV1QD8MLZFc35c"
REFRESH_TOKEN = "AMf-vByDvonlbf_sQ3yPRdZkpYLEsVLaU8LTH_znUizaQRXcUxfu2qfsUMcRmPKO8qfpcMgv8s-3R3kjLrnzUG7M1Mq_JToL1nP04rB6ySCEGW1vdMuFEcxFRFrz7zyZczb2-ok4FjkWVJN2RX_SHkW3AznNEYFA_Xn-u9NYCADasuNkpebmOVs85AqYhyBaGFXPITfs3pfzbcZDGlRo7ZpGug8zvcgYEBxP5KDc71wsCQb7OTLECew"
CACHE_FILE = "token_cache.json"
BUFFER_MINUTES = 5

## DISCOVERY PLUS+
DPLUS_ACCESS_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJVU0VSSUQ6ZHBsdXNpbmRpYTphMmY0ODlkNi05ZjBjLTQ5NjQtYWYxNi04YTBhYjIzNjMyZTkiLCJqdGkiOiJ0b2tlbi1kOTUzODc0ZC1lOGMyLTQ0N2YtYjBiMS0yNjA5ZWEzY2QzYzYiLCJhbm9ueW1vdXMiOmZhbHNlLCJpYXQiOjE3NTA5NDM3Mjh9.gj3brc9rnd3HtkbPh7kUxND-hBxnrGc2ZIRNmWK56bQ'

## SONY LIV
DEVICE_ID = "e55eac3f6aa64c218808aa516f905c2b-1752249266062"
SESSION_ID = "fbc757d6d9c94a6dbb5728a0529ba457-1739253569224"
AUTHORIZATION_TOKEN = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiIyMjEwMjUxNTExMjk3NDAwNTAxIiwidG9rZW4iOiJmbWVYLUxGcXktM0NjNi1kV3VVLW10bEUtRFIxUi04aCIsImV4cGlyYXRpb25Nb21lbnQiOiIyMDI2LTA3LTExVDE1OjU1OjEzLjkxNVoiLCJpc1Byb2ZpbGVDb21wbGV0ZSI6dHJ1ZSwic2Vzc2lvbkNyZWF0aW9uVGltZSI6IjIwMjUtMDctMTFUMTU6NTU6MTMuOTE2WiIsImNoYW5uZWxQYXJ0bmVySUQiOiJNU01JTkQiLCJmaXJzdE5hbWUiOiJNYWhlc2giLCJtb2JpbGVOdW1iZXIiOiI4MzMxOTE1NTc4IiwiZGF0ZU9mQmlydGgiOjYzOTI1MzgwMDAwMCwiZ2VuZGVyIjoiTWFsZSIsInByb2ZpbGVQaWMiOiJodHRwczovL29yaWdpbi1zdGF0aWN2Mi5zb255bGl2LmNvbS9VSV9pY29ucy9Nb2JpbGVfQXZhdGFyc18wMy5wbmciLCJzb2NpYWxQcm9maWxlUGljIjoiIiwic29jaWFsTG9naW5JRCI6bnVsbCwic29jaWFsTG9naW5UeXBlIjpudWxsLCJpc0VtYWlsVmVyaWZpZWQiOnRydWUsImlzTW9iaWxlVmVyaWZpZWQiOnRydWUsImxhc3ROYW1lIjoiIiwiZW1haWwiOiJkaGFuYWxha3NobWlrYWRhbGkxOTkwQGdtYWlsLmNvbSIsImlzQ3VzdG9tZXJFbGlnaWJsZUZvckZyZWVUcmlhbCI6ZmFsc2UsImNvbnRhY3RJRCI6IjMyODY5MjA2MiIsImlhdCI6MTc1MjI0OTMxNCwiZXhwIjoxNzgzNzg1MzE0fQ.MsOw2GR5N_UsPNfgm7zuYkuMPLzLgfTePadl2SUZq3c"

## ULLU
AUTH_TOKEN =  "Bearer f0c1e4e9-1cc0-416e-9b22-d03c98bafbaa"
