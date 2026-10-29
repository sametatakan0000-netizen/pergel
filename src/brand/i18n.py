"""Pergel i18n — the global-first UI dictionary.

Eight complete locales (tr, en, de, es, fr, ru, ar, zh). Every locale maps
the SAME key set as English (en is the source of truth); surfaces mark
strings with ``data-i18n`` / ``data-i18n-ph`` hooks and ``i18n_js()`` swaps
them at load based on ``localStorage.pergel_lang`` or ``navigator.language``.
RTL scripts (ar/he/fa/ur) get ``dir="rtl"`` automatically.
"""


import json

LOCALES: dict = {
    "en": {
        "title": "New Tab",
        "search_ph": "Search the web or type a URL",
        "cmd_ph": "Search or find a tab",
        "web": "Web",
        "ai_mode": "AI Mode",
        "synthesize": "Synthesize with AI Mode",
        "customize": "Customize Pergel",
        "ntp_ext": "Pergel NTP — click",
        "new_incognito": "Open in incognito window",
        "export_html": "Export bookmarks (HTML)",
        "bm_folder": "Pergel Bookmarks",
        "panel_title": "Pergel AI",
        "tabs_label": "Tabs",
        "sentez_prompt": "summarize and compare these: ",
        "shield_label": "Pergel Shield",
        "blocked_today": "requests blocked today",
        "language": "Language",
    },
    "tr": {
        "title": "Yeni Sekme",
        "search_ph": "Web'de arayın veya URL yazın",
        "cmd_ph": "Ara veya sekme bul",
        "web": "Web",
        "ai_mode": "AI Modu",
        "synthesize": "AI Modu ile sentezle",
        "customize": "Pergel'i Özelleştir",
        "ntp_ext": "Pergel NTP — tıkla",
        "new_incognito": "Gizli sekmede aç",
        "export_html": "Yer imlerini dışa aktar (HTML)",
        "bm_folder": "Pergel Yer İmleri",
        "panel_title": "Pergel AI",
        "tabs_label": "Sekmeler",
        "sentez_prompt": "şunları özetle ve karşılaştır: ",
        "shield_label": "Pergel Kalkan",
        "blocked_today": "bugün engellenen istek",
        "language": "Dil",
    },
    "de": {
        "title": "Neuer Tab",
        "search_ph": "Im Web suchen oder URL eingeben",
        "cmd_ph": "Suchen oder Tab finden",
        "web": "Web",
        "ai_mode": "KI-Modus",
        "synthesize": "Mit KI-Modus synthetisieren",
        "customize": "Pergel anpassen",
        "ntp_ext": "Pergel NTP — klicken",
        "new_incognito": "In Inkognitofenster öffnen",
        "export_html": "Lesezeichen exportieren (HTML)",
        "bm_folder": "Pergel-Lesezeichen",
        "panel_title": "Pergel KI",
        "tabs_label": "Tabs",
        "sentez_prompt": "fasse zusammen und vergleiche: ",
        "shield_label": "Pergel Schutzschild",
        "blocked_today": "heute blockierte Anfragen",
        "language": "Sprache",
    },
    "es": {
        "title": "Nueva pestaña",
        "search_ph": "Buscar en la web o escribir una URL",
        "cmd_ph": "Buscar o encontrar una pestaña",
        "web": "Web",
        "ai_mode": "Modo IA",
        "synthesize": "Sintetizar con Modo IA",
        "customize": "Personalizar Pergel",
        "ntp_ext": "Pergel NTP — clic",
        "new_incognito": "Abrir en ventana de incógnito",
        "export_html": "Exportar marcadores (HTML)",
        "bm_folder": "Marcadores de Pergel",
        "panel_title": "Pergel IA",
        "tabs_label": "Pestañas",
        "sentez_prompt": "resume y compara: ",
        "shield_label": "Escudo Pergel",
        "blocked_today": "solicitudes bloqueadas hoy",
        "language": "Idioma",
    },
    "fr": {
        "title": "Nouvel onglet",
        "search_ph": "Rechercher sur le web ou saisir une URL",
        "cmd_ph": "Rechercher ou trouver un onglet",
        "web": "Web",
        "ai_mode": "Mode IA",
        "synthesize": "Synthétiser avec le Mode IA",
        "customize": "Personnaliser Pergel",
        "ntp_ext": "Pergel NTP — cliquer",
        "new_incognito": "Ouvrir en navigation privée",
        "export_html": "Exporter les favoris (HTML)",
        "bm_folder": "Favoris Pergel",
        "panel_title": "Pergel IA",
        "tabs_label": "Onglets",
        "sentez_prompt": "résume et compare : ",
        "shield_label": "Bouclier Pergel",
        "blocked_today": "requêtes bloquées aujourd'hui",
        "language": "Langue",
    },
    "ru": {
        "title": "Новая вкладка",
        "search_ph": "Поиск в интернете или введите URL",
        "cmd_ph": "Поиск или найдите вкладку",
        "web": "Web",
        "ai_mode": "ИИ-режим",
        "synthesize": "Синтезировать в ИИ-режиме",
        "customize": "Настроить Pergel",
        "ntp_ext": "Pergel NTP — нажмите",
        "new_incognito": "Открыть в окне инкогнито",
        "export_html": "Экспорт закладок (HTML)",
        "bm_folder": "Закладки Pergel",
        "panel_title": "Pergel ИИ",
        "tabs_label": "Вкладки",
        "sentez_prompt": "обобщи и сравни: ",
        "shield_label": "Щит Pergel",
        "blocked_today": "заблокированных запросов сегодня",
        "language": "Язык",
    },
    "ar": {
        "title": "تبويب جديد",
        "search_ph": "ابحث في الويب أو اكتب عنوان URL",
        "cmd_ph": "ابحث أو أجد تبويبًا",
        "web": "الويب",
        "ai_mode": "وضع الذكاء الاصطناعي",
        "synthesize": "توليد عبر وضع الذكاء الاصطناعي",
        "customize": "تخصيص Pergel",
        "ntp_ext": "Pergel NTP — انقر",
        "new_incognito": "فتح في نافذة تصفح خاص",
        "export_html": "تصدير العلامات المرجعية (HTML)",
        "bm_folder": "علامات Pergel المرجعية",
        "panel_title": "Pergel AI",
        "tabs_label": "علامات التبويب",
        "sentez_prompt": "لخّص وقارن: ",
        "shield_label": "درع Pergel",
        "blocked_today": "الطلبات المحظورة اليوم",
        "language": "اللغة",
    },
    "zh": {
        "title": "新标签页",
        "search_ph": "搜索网络或输入网址",
        "cmd_ph": "搜索或查找标签页",
        "web": "网页",
        "ai_mode": "AI 模式",
        "synthesize": "用 AI 模式合成",
        "customize": "自定义 Pergel",
        "ntp_ext": "Pergel NTP — 点击",
        "new_incognito": "在无痕窗口打开",
        "export_html": "导出书签 (HTML)",
        "bm_folder": "Pergel 书签",
        "panel_title": "Pergel AI",
        "tabs_label": "标签页",
        "sentez_prompt": "总结并比较：",
        "shield_label": "Pergel 防护",
        "blocked_today": "今日已拦截请求",
        "language": "语言",
    },
}

RTL_LANGS = ("ar", "he", "fa", "ur")


def i18n_js() -> str:
    """The client-side applier: pick locale, swap hooks, set lang/dir,
    wire the language selector (persisted in localStorage)."""
    table = json.dumps(LOCALES, ensure_ascii=False)
    rtl = json.dumps(list(RTL_LANGS))
    return (
        "(function(){\n"
        f"const I18N = {table}; const RTL = {rtl};\n"
        "const pick = (localStorage.pergel_lang ||\n"
        "  navigator.language || 'en').slice(0, 2).toLowerCase();\n"
        "const lang = I18N[pick] ? pick : 'en'; const d = I18N[lang];\n"
        "window.T = d; document.documentElement.lang = lang;\n"
        "if (RTL.indexOf(lang) >= 0) document.documentElement.dir = 'rtl';\n"
        "document.querySelectorAll('[data-i18n]').forEach(function(el){\n"
        "  if (d[el.dataset.i18n]) el.textContent = d[el.dataset.i18n]; });\n"
        "document.querySelectorAll('[data-i18n-ph]').forEach(function(el){\n"
        "  if (d[el.dataset.i18nPh]) el.placeholder = d[el.dataset.i18nPh]; });\n"
        "const sel = document.getElementById('lang-select');\n"
        "if (sel) { sel.value = lang; sel.onchange = function(){\n"
        "  localStorage.pergel_lang = sel.value; location.reload(); }; }\n"
        "})();\n"
    )


LANG_LABELS = (
    ("en", "English"), ("tr", "Türkçe"), ("de", "Deutsch"),
    ("es", "Español"), ("fr", "Français"), ("ru", "Русский"),
    ("ar", "العربية"), ("zh", "中文"),
)


def lang_links(current: str = "en") -> str:
    """Scriptless language switcher for the NTP: plain anchors to the
    pre-rendered ``pergel_ntp_<code>.html`` variants."""
    out = []
    for code, label in LANG_LABELS:
        cur = ' aria-current="page"' if code == current else ""
        out.append(f'<a href="pergel_ntp_{code}.html"{cur}>{label}</a>')
    return "".join(out)


def lang_selector() -> str:
    """The always-available language picker (flag-free, text only)."""
    opts = "".join(f'<option value="{code}">{label}</option>'
                   for code, label in LANG_LABELS)
    return (f'<select id="lang-select" aria-label="language">{opts}</select>')
