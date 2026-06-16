"""Эвристики: определить категорию / бренд / ECU по пути и имени файла."""
import re

# категория по расширению
EXT_CATEGORY = {
    # прошивки / дампы
    **{e: "firmware" for e in (
        "bin", "ori", "mod", "ecu", "dam", "kp", "frf", "sgo", "a2l", "hex",
        "s19", "full", "read", "ews", "dtf", "cwf", "ols", "damos", "kess", "ktag")},
    # документы
    **{e: "document" for e in (
        "pdf", "doc", "docx", "chm", "txt", "rtf", "xls", "xlsx", "ppt", "pptx", "djvu")},
    # картинки
    **{e: "image" for e in ("jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp")},
    # видео
    **{e: "video" for e in ("mkv", "avi", "mp4", "mov", "wmv", "webm", "flv", "mpg", "mpeg")},
    # софт / архивы
    **{e: "software" for e in ("exe", "msi", "dll", "rar", "zip", "7z", "cab", "iso")},
    # данные
    **{e: "data" for e in ("dat", "csv", "xml", "json", "ini", "cfg", "db")},
    # аудио
    **{e: "audio" for e in ("mp3", "wav", "ogg", "flac", "m4a")},
}

# бренд: ключевое слово (верхний регистр) -> нормализованное имя
BRANDS = [
    (r"MERCEDES|BENZ|\bMB\b|AMG", "Mercedes-Benz"),
    (r"\bBMW\b|\bMINI\b", "BMW"),
    (r"\bAUDI\b|\bVW\b|VOLKSWAGEN|\bVAG\b|SKODA|SEAT", "VAG"),
    (r"TOYOTA|LEXUS", "Toyota/Lexus"),
    (r"NISSAN|INFINITI|DATSUN", "Nissan"),
    (r"\bFORD\b|VISTEON", "Ford"),
    (r"\bOPEL\b|VAUXHALL", "Opel"),
    (r"RENAULT|DACIA", "Renault"),
    (r"PEUGEOT|CITROEN|\bPSA\b", "PSA"),
    (r"\bFIAT\b|ALFA|LANCIA|ABARTH", "Fiat/Alfa"),
    (r"HYUNDAI|\bKIA\b|KEFICO", "Hyundai/Kia"),
    (r"MAZDA", "Mazda"),
    (r"HONDA|ACURA", "Honda"),
    (r"MITSUBISHI|\bFUSO\b", "Mitsubishi"),
    (r"\bVOLVO\b", "Volvo"),
    (r"LADA|\bVAZ\b|ВАЗ|КАЛИНА|ПРИОРА|ГРАНТА|НИВА", "Lada/VAZ"),
    (r"GAZ|ГАЗ|УАЗ|\bUAZ\b|КАМАЗ|KAMAZ|МАЗ", "ГАЗ/УАЗ/КАМАЗ"),
    (r"\bMAN\b", "MAN"),
    (r"SCANIA", "Scania"),
    (r"\bDAF\b", "DAF"),
    (r"IVECO", "Iveco"),
    (r"CUMMINS", "Cummins"),
    (r"CATERPILLAR|\bCAT\b", "Caterpillar"),
    (r"JOHN ?DEERE", "John Deere"),
    (r"PERKINS", "Perkins"),
    (r"DEUTZ", "Deutz"),
    (r"CHEVROLET|\bGM\b|CADILLAC|BUICK", "GM"),
    (r"SUBARU", "Subaru"),
    (r"SUZUKI", "Suzuki"),
    (r"SSANGYONG", "SsangYong"),
    (r"LAND ?ROVER|JAGUAR|\bJLR\b", "JLR"),
    (r"PORSCHE", "Porsche"),
]
BRANDS = [(re.compile(p), n) for p, n in BRANDS]

# ECU / платформа
ECUS = [
    (r"EDC17\w*", "Bosch EDC17"),
    (r"EDC16\w*", "Bosch EDC16"),
    (r"EDC15\w*", "Bosch EDC15"),
    (r"MED17\w*|MED9\w*|MEDC17\w*", "Bosch MED17/MED9"),
    (r"\bME7\b|\bME9\b|MEV\w*", "Bosch ME7/MEV"),
    (r"\bMG1\w*|\bMD1\w*|MDG1\w*", "Bosch MG1/MD1"),
    (r"\bMSV\w*|\bMSD\w*|\bMSS\w*", "Bosch MSV/MSD"),
    (r"SIMOS\w*", "Siemens Simos"),
    (r"\bSID\d\w*|\bSIM\d\w*|\bPCR\d\w*", "Siemens/Continental SID/SIM/PCR"),
    (r"DELPHI|DCM\d\w*", "Delphi"),
    (r"MARELLI|\bMJD\b|IAW\w*", "Magneti Marelli"),
    (r"DENSO", "Denso"),
    (r"SH720\d\d|SH705\d", "Renesas SH7xxx"),
    (r"TRICORE|TC17\d\d|TC2\d\d", "Infineon TriCore"),
    (r"MPC5\d\d", "Freescale MPC5xxx"),
    (r"\bM(7\.9\.7|17\.9\.7|74|75|86)\b", "ЭБУ Январь/M74/M75 (VAZ)"),
]
ECUS = [(re.compile(p), n) for p, n in ECUS]


def classify(path: str, ext: str) -> tuple[str, str | None, str | None]:
    up = path.upper()
    category = EXT_CATEGORY.get(ext.lower(), "other")
    brand = next((n for rx, n in BRANDS if rx.search(up)), None)
    ecu = next((n for rx, n in ECUS if rx.search(up)), None)
    return category, brand, ecu
