import pytest

from app.integrations.release_languages import detect_audio_languages, detect_audio_track_count


@pytest.mark.parametrize(
    ("title", "description", "labels", "expected"),
    [
        ("Movie 2019 WEB-DL", "流浪地球 [国语/中英双字]", ("中字",), ("国语",)),
        ("Movie 2003 2Audios", "无间道2 [国粤双语/中英字幕]", (), ("国语", "粤语")),
        ("Movie 2006", "国{六区}法英三语 简繁双语四字幕/国配简繁双语四特效字幕", (), ("国语", "英语", "法语")),
        ("Parasite 2019 DDP5.1 [HIN+KOR+TAM] ESUB", "寄生虫", (), ("韩语", "印地语")),
        ("Movie 2021", "*日语*多国语字幕*", (), ("日语",)),
        ("Inception 2010 3D", "中英立体字幕 中英音轨", (), ("国语", "英语")),
        ("Inception 2010", "原盘简体/繁体/简英双语/繁英双语", (), ()),
        ("Movie 2020", "中英双语硬字幕", (), ()),
        ("Movie 2020", "[国语中字] 英语字幕", (), ("国语",)),
        ("Movie 2020", "", ("中配", "中字"), ("国语",)),
        ("Movie 2020 Cantonese", "", (), ("粤语",)),
    ],
)
def test_detect_audio_languages(title: str, description: str, labels: tuple[str, ...], expected: tuple[str, ...]) -> None:
    assert detect_audio_languages(title, description, labels) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Movie 2010 BluRay 4Audio-FRDS", 4),
        ("Movie 2003 DDP5.1 2Audios-UBWEB", 2),
        ("Movie 2010 17Audio-DIY@UBits", 17),
        ("Movie 2010 DDP5.1-HHWEB", 0),
    ],
)
def test_detect_audio_track_count(title: str, expected: int) -> None:
    assert detect_audio_track_count(title) == expected
