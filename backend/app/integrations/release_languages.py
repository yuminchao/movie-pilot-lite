import re

# 中文缩写字 → 音轨语言；用于「国粤双语」「中英音轨」这类紧凑写法
_SHORT_NAMES = {
    "国": "国语",
    "中": "国语",
    "粤": "粤语",
    "英": "英语",
    "日": "日语",
    "韩": "韩语",
    "法": "法语",
    "德": "德语",
    "意": "意大利语",
    "西": "西班牙语",
    "俄": "俄语",
    "泰": "泰语",
}

# 完整中文词 → 音轨语言
_FULL_NAMES = {
    "国语": "国语",
    "普通话": "国语",
    "国配": "国语",
    "台配": "国语",
    "中配": "国语",
    "粤语": "粤语",
    "粤配": "粤语",
    "英语": "英语",
    "英配": "英语",
    "日语": "日语",
    "韩语": "韩语",
    "法语": "法语",
    "德语": "德语",
    "意大利语": "意大利语",
    "西班牙语": "西班牙语",
    "俄语": "俄语",
    "泰语": "泰语",
    "印地语": "印地语",
}

# 英文名或 ISO 639 三字母代码 → 音轨语言
_CODES = {
    "MANDARIN": "国语",
    "CHI": "国语",
    "CHN": "国语",
    "CMN": "国语",
    "CANTONESE": "粤语",
    "YUE": "粤语",
    "CAN": "粤语",
    "ENG": "英语",
    "JPN": "日语",
    "JAP": "日语",
    "KOR": "韩语",
    "FRE": "法语",
    "FRA": "法语",
    "GER": "德语",
    "DEU": "德语",
    "ITA": "意大利语",
    "SPA": "西班牙语",
    "RUS": "俄语",
    "THA": "泰语",
    "HIN": "印地语",
}

# 展示顺序：常用语言在前
_ORDER = ["国语", "粤语", "英语", "日语", "韩语", "法语", "德语", "意大利语", "西班牙语", "俄语", "泰语", "印地语"]

# 「国粤双语」「法英三语」「中英音轨」；后面紧跟「字幕/字」时是字幕说明，不计入音轨
_COMPACT = re.compile(r"([国中粤英日韩法德意西俄泰简繁]{2,6})([双三四五多]语|音轨)(?!\s*(?:字幕|字|硬字))")
_FULL = re.compile("(" + "|".join(sorted(_FULL_NAMES, key=len, reverse=True)) + r")(?!\s*字)")
# 「[HIN+ENG+TAM]」这类多音轨代码列表
_CODE_LIST = re.compile(r"\b([A-Z]{3}(?:\s*[+/]\s*[A-Z]{3})+)\b")
# 只认 Mandarin/Cantonese：English、Japanese 常出现在片名里，误判多
_ENGLISH_WORD = re.compile(r"\b(MANDARIN|CANTONESE)\b", re.IGNORECASE)
_AUDIO_COUNT = re.compile(r"\b(\d{1,2})\s*Audios?\b", re.IGNORECASE)


def detect_audio_languages(title: str, description: str, labels: tuple[str, ...]) -> tuple[str, ...]:
    """从站点标签、标题与副标题中推断资源包含的音轨语言。

    M-Team 没有结构化的语言字段，只能依据「中配」标签、
    「国粤双语」「[国语/中字]」「[HIN+ENG]」等发布惯用写法做启发式识别；
    只写字幕语言（如「中英双字」「简英双语字幕」）的不计入音轨。

    Args:
        title: 资源英文标题。
        description: 资源副标题。
        labels: 站点标签，如「中配」「中字」。

    Returns:
        按常用度排序、去重后的音轨语言名称；识别不到时为空。
    """
    found: set[str] = set()
    if "中配" in labels:
        found.add("国语")
    text = f"{title} {description}"
    for match in _COMPACT.finditer(text):
        chars, suffix = match.groups()
        # 含「简/繁」的是字幕写法（简英双语）；不带「音轨」的「中英双语」多指字幕
        if "简" in chars or "繁" in chars or ("中" in chars and suffix != "音轨"):
            continue
        found.update(_SHORT_NAMES[char] for char in chars if char in _SHORT_NAMES)
    for match in _FULL.finditer(text):
        found.add(_FULL_NAMES[match.group(1)])
    for match in _CODE_LIST.finditer(title):
        codes = re.split(r"\s*[+/]\s*", match.group(1))
        found.update(_CODES[code] for code in codes if code in _CODES)
    for match in _ENGLISH_WORD.finditer(title):
        found.add(_CODES[match.group(1).upper()])
    return tuple(language for language in _ORDER if language in found)


def detect_audio_track_count(title: str) -> int:
    """从标题中的「2Audio」「4Audios」读取音轨数量。

    Args:
        title: 资源英文标题。

    Returns:
        标题声明的音轨数量；未声明时为 0。
    """
    match = _AUDIO_COUNT.search(title)
    return int(match.group(1)) if match else 0
