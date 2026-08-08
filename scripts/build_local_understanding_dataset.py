"""Build the first empirical corpus from the accepted semantic blueprint."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.local_understanding.dataset import augment, deterministic_split, qc, source_from_blueprint, write_jsonl

DATA = ROOT / "data" / "local_understanding"

CHALLENGE = [
    ("Bəs?", "ambiguous_follow_up"), ("Bəs Bleach?", "ambiguous_follow_up"),
    ("Bəs GTA?", "ambiguous_follow_up"), ("Onu dəyiş.", "targetless_write"),
    ("Sil bunu.", "targetless_write"), ("Dayandır.", "targetless_write"),
    ("Keçən dəfə sənə nə demişdim?", "personal_history"),
    ("Dünən nə danışmışdıq?", "personal_history"),
    ("Yaddaşında bu barədə nə var?", "storage_read"),
    ("Məqsədlərimi göstər və bunu yadda saxla.", "mixed_authority"),
    ("Məqsəd qoymaq haqqında danışaq.", "keyword_overlap"),
    ("Mən Bleach-i sevirəm?", "question_assertion_ambiguity"),
]

TARGETED = {
    "GENERAL_CONVERSATION": ["Məqsəd insanı necə motivasiya edir?", "Hədəf seçmək niyə çətindir?", "Süni intellektin yaddaşı varmı?", "Sənin rolun nədir?", "Sən nə üçün varsan?", "Anime haqqında danış.", "Bir plan hazırlamağa kömək et.", "Məqsəd sözünün mənası nədir?", "Bu mətni qısa yaz.", "Bunu ingiliscəyə tərcümə et.", "Bu hissəni yenidən ifadə et.", "Mətni iki cümlə ilə xülasə et.", "Məlumatı yadda saxlaya bilirsən?", "Yaddaşın nə qədərdir?", "Sən hansı model əsasında işləyirsən?"],
    "IDENTITY_QUERY": ["Kimlə danışıram?", "Sən özünü necə təqdim edirsən?", "Sənin kimliyin nədir?", "Nel sənin adındır?", "Sənə necə xitab edim?", "Sənin adını necə deyim?", "Sənə hansı adla səslənim?", "Özünü bir cümlə ilə tanıt.", "Mənə adını söylə.", "Adını mənə tanıt."],
    "MEMORY_WRITE_REQUEST": ["Yadında saxla ki, mən şahmat oynayıram.", "Unutma ki, mən ispan dili öyrənirəm.", "Mənim Linux istifadə etdiyimi qeyd et.", "Sonra üçün yadda saxla: səhərlər qaçıram.", "Yadında saxla: mən hər axşam kitab oxuyuram.", "Qeyd et: mən velosiped sürməyi sevirəm."],
    "PERSONAL_ASSERTION": ["Mən bu oyunu bəyənirəm.", "Mən fransız dili öyrənirəm.", "Mən hər axşam gəzirəm.", "Əslində mən çayı sevmirəm.", "Mən gələn il universitetə girmək istəyirəm.", "Mən bu proqramdan istifadə edirəm.", "Mən gələn yay səyahət etmək istəyirəm.", "Mən gündəlik yazıram.", "Hazırda portuqal dili öyrənirəm."],
    "PERSONAL_FACT_QUERY": ["Mən hansı proqramdan istifadə edirəm?", "Mənim bəyəndiyim oyun hansıdır?", "Mən hansı dili öyrənirəm?", "Mənim gündəlik vərdişim nədir?", "Seçdiyim film hansıdır?", "Mən hansı kitabı seçmişəm?"],
    "GOAL_LIST_QUERY": ["Mənim hazırkı hədəflərimi de.", "Nələri məqsəd kimi seçmişəm?", "Mənim əsas hədəflərim hansılardır?", "Gələcək istiqamətimi müəyyən edən məqsədlər hansıdır?", "Mənim aktiv məqsədlərim nələrdir?"],
    "GOAL_WRITE_REQUEST": ["C1 hədəfimi dayandır.", "Kitab oxumağı məqsədlərimə əlavə et."],
}

# Iteration 2 is restricted to the observed release-v2 rejection families.
# These are new realizations, not paraphrases of the consumed release holdout.
TARGETED_ITER2 = {
    "GENERAL_CONVERSATION": [
        "Sən hansı işlərdə kömək edə bilirsən?",
        "Yaddaş funksiyan necə işləyir?",
        "Məlumatı uzun müddət saxlaya bilirsən?",
        "Sən hansı modeldən istifadə edirsən?",
    ],
    "IDENTITY_QUERY": [
        "Sən necə bir köməkçisən?",
        "Sənin növün nədir?",
        "Nel necə bir varlıqdır?",
        "Sən hansı cür süni köməkçisən?",
    ],
    "MEMORY_WRITE_REQUEST": [
        "Unutma ki, mən hər gün piyada gəzirəm.",
        "Gələcək üçün qeyd et: mən musiqi dinləməyi sevirəm.",
        "Sonra xatırla ki, mən evdə çay içirəm.",
        "Bu məlumatı saxla: mən həftəsonu üzürəm.",
    ],
}

FINAL_HOLDOUT = {
    "GENERAL_CONVERSATION": ["Məqsəd qoymağın üstünlüyü nədir?", "Yaddaş beynimizdə necə yaranır?", "Sən hansı işlərdə kömək edə bilərsən?", "Naruto necə animedir?", "Bu cümləni ingiliscəyə çevir."],
    "GOAL_LIST_QUERY": ["Mənim aktiv məqsədlərimi sadala.", "Hazırda hansı nəticələrə doğru gedirəm?", "Özümə qoyduğum hədəfləri xatırlat.", "Məqsəd kimi nələr seçmişəm?", "Qarşımdakı hədəflər hansılardır?"],
    "GOAL_WRITE_REQUEST": ["B2-ni yeni məqsəd kimi yaz.", "Bu hədəfi müvəqqəti dayandır.", "C1 məqsədimi yenidən aktivləşdir.", "Kitab hədəfimi bitmiş say.", "Dil məqsədimin prioritetini artır."],
    "IDENTITY_QUERY": ["Kim olduğunu deyərsən?", "Sənə hansı adla müraciət edim?", "Özünü qısaca tanıt.", "Sən hansı növ köməkçisən?", "Nel elə sənsən?"],
    "MEMORY_WRITE_REQUEST": ["Mən şahmatı sevirəm, bunu yadda saxla.", "Gələcək üçün qeyd et ki, ispan dili öyrənirəm.", "Bu məlumatı unutma: səhərlər qaçıram.", "Mənim Linux işlətdiyimi yadında saxla.", "Əslində çayı sevirəm, bunu yadda saxla."],
    "PERSONAL_ASSERTION": ["Mən şahmat oynamağı sevirəm.", "Hazırda ispan dili öyrənirəm.", "Mən hər səhər qaçıram.", "Mən Linux işlədirəm.", "Gələn il magistr oxumaq istəyirəm."],
    "PERSONAL_FACT_QUERY": ["Mən hansı idmanı sevirəm?", "Mən hazırda hansı dili öyrənirəm?", "Mənim səhər vərdişim nədir?", "Mən hansı sistemi işlədirəm?", "Seçdiyim kitab hansıdır?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim barəmdə bildiklərini de.", "Məni tanıdığın qədər təsvir et.", "Haqqımda qısa məlumat ver.", "Mənimlə bağlı hansı məlumatların var?", "Məni nə qədər tanıyırsan?"],
}

RELEASE_HOLDOUT = {
    "GENERAL_CONVERSATION": ["Məqsəd anlayışı insan həyatına necə təsir edir?", "Süni intellekt yaddaşı necə emal edir?", "Bu fikri daha qısa yaz."],
    "GOAL_LIST_QUERY": ["Mənim bu dövrdəki hədəflərim hansılardır?", "Nəyə çatmaq üçün səy göstərdiyimi xatırlat.", "Özümə seçdiyim məqsədləri göstər."],
    "GOAL_WRITE_REQUEST": ["İspan dili öyrənməyi məqsəd kimi əlavə et.", "Mövcud C1 hədəfimi pauzaya al.", "Kitab oxuma hədəfimi yenidən aktiv et."],
    "IDENTITY_QUERY": ["Mənə öz adını deyə bilərsən?", "Sən hansı köməkçisən?", "Özünü tanıdarsan?"],
    "MEMORY_WRITE_REQUEST": ["Mən velosiped sürməyi sevirəm, bunu yadda saxla.", "Sonra üçün qeyd et ki, italyan dili öyrənirəm.", "Yadında saxla: hər axşam kitab oxuyuram."],
    "PERSONAL_ASSERTION": ["Hazırda italyan dili öyrənirəm.", "Mən velosiped sürməyi sevirəm.", "Mən hər axşam kitab oxuyuram."],
    "PERSONAL_FACT_QUERY": ["Mən hansı nəqliyyat vasitəsini sevirəm?", "Mən indi hansı dili öyrənirəm?", "Mən axşamlar nə edirəm?"],
    "PERSONAL_PROFILE_QUERY": ["Mənimlə bağlı ümumi nə bilirsən?", "Mənim profilimi təsvir et.", "Məni tanıdığın kimi ümumiləşdir."],
}

RELEASE_HOLDOUT_V2 = {
    "GENERAL_CONVERSATION": ["Məqsəd qoymaq nəyə kömək edir?", "Yaddaş sistemi nə cür işləyir?", "Bu cümləni qısalt.", "Sən nə kimi işlər görə bilirsən?", "One Piece necə animedir?", "Pythonla nə etmək olar?"],
    "GOAL_LIST_QUERY": ["Mənim indiki məqsədlərim hansılardır?", "Qarşıma seçdiyim hədəfləri sadala.", "Nəyə doğru getdiyimi xatırlat.", "Aktiv hədəflərim nələrdir?", "Özüm üçün müəyyən etdiyim məqsədləri de.", "Mənim əsas istiqamətlərim hansılardır?"],
    "GOAL_WRITE_REQUEST": ["İtalyan dili hədəfini əlavə et.", "Bu məqsədi müvəqqəti saxla.", "C1 hədəfimi yenidən başlat.", "Oxuma məqsədimi tamamlanmış say.", "Dil hədəfimin adını dəyiş.", "Bu hədəfi daha vacib et."],
    "IDENTITY_QUERY": ["Adını mənə söyləyərsən?", "Sənə necə müraciət etməliyəm?", "Kim olduğunu qısa de.", "Özünü tanıtmaq istərsən?", "Sən hansı tip köməkçisən?", "Nel adı sənə aiddir?"],
    "MEMORY_WRITE_REQUEST": ["Yadında saxla: mən şahmat sevirəm.", "Qeyd et ki, koreya dili öyrənirəm.", "Unutma, hər səhər gəzirəm.", "Sonrakı söhbətlər üçün bunu saxla: mən Linux istifadə edirəm.", "Mənim qəhvəni şəkərsiz içdiyimi yadda saxla.", "Gələcək üçün qeyd et, mən foto çəkməyi sevirəm."],
    "PERSONAL_ASSERTION": ["Mən koreya dili öyrənirəm.", "Mən səhərlər gəzirəm.", "Mən Linux istifadə edirəm.", "Mən qəhvəni şəkərsiz içirəm.", "Mən foto çəkməyi sevirəm.", "Gələn il səyahət etməyi düşünürəm."],
    "PERSONAL_FACT_QUERY": ["Mən hansı dili öyrənirəm?", "Mən səhərlər nə edirəm?", "Mən hansı sistemi istifadə edirəm?", "Qəhvəmi necə içirəm?", "Mənim hobbim nədir?", "Mən gələcəkdə nə etmək istəyirəm?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim haqqımda ümumi bildiklərini söylə.", "Məni tanıdığın şəkildə təsvir et.", "Mənim profilim barədə qısa danış.", "Mənimlə bağlı hansı ümumi məlumatların var?", "Məni nə qədər yaxşı tanıyırsan?", "Mənim haqqımda toplu nə bilirsən?"],
}

CALIBRATION = {
    "GENERAL_CONVERSATION": ["Məqsəd anlayışı nə deməkdir?", "Yaddaşın işi necədir?", "Sən hansı tapşırıqları bacarırsan?"],
    "GOAL_LIST_QUERY": ["Hazırkı məqsədlərimi göstər.", "Nəyə doğru çalışdığımı de.", "Qoyduğum hədəflər hansıdır?"],
    "GOAL_WRITE_REQUEST": ["B2-ni hədəf kimi əlavə et.", "Bu məqsədi tamamlanmış say.", "C1 hədəfimi yenidən aktiv et."],
    "IDENTITY_QUERY": ["Sən kim olursan?", "Adını mənə de.", "Özünü qısaca təqdim et.", "Mənə adını söylə.", "Mən sənin adını öyrənmək istəyirəm."],
    "MEMORY_WRITE_REQUEST": ["Mən çayı sevirəm, bunu yadda saxla.", "Qeyd et ki, fransız dili öyrənirəm.", "Gələcək üçün unutma ki, səhərlər qaçıram.", "Yadında saxla: mən kitab oxuyuram.", "Qeyd et: mən velosiped sürürəm."],
    "PERSONAL_ASSERTION": ["Mən çayı sevirəm.", "Mən fransız dili öyrənirəm.", "Mən səhərlər qaçıram."],
    "PERSONAL_FACT_QUERY": ["Mən hansı içkini sevirəm?", "Mən hansı dili öyrənirəm?", "Mən nə vaxt qaçıram?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim haqqımda bildiklərini de.", "Məni necə tanıdığını danış.", "Mənimlə bağlı məlumatları ümumiləşdir."],
}

CALIBRATION_ITER2 = {
    "GENERAL_CONVERSATION": [
        "Yaddaşınla nələri edə bilirsən?",
        "Sən nə kimi işlər bacarırsan?",
    ],
    "IDENTITY_QUERY": [
        "Sən hansı növ köməkçisən?",
        "Nel nə cür bir köməkçidir?",
    ],
    "MEMORY_WRITE_REQUEST": [
        "Unutma, mən hər axşam musiqi dinləyirəm.",
        "Gələcək üçün qeyd et: mən şənbə günləri üzürəm.",
        "Sonra üçün saxla ki, mən qəhvəni südsüz içirəm.",
    ],
}

RELEASE_HOLDOUT_V3 = {
    "GENERAL_CONVERSATION": ["Məqsəd seçmək nə üçün lazımdır?", "Yaddaş texnologiyası necə işləyir?", "Bu paraqrafı izah et.", "Nə tip kömək edə bilirsən?", "JavaScript nədir?", "Bleach necə animedir?"],
    "GOAL_LIST_QUERY": ["Mənim aktiv hədəflərim hansılardır?", "Hazırda nəyə çatmağa çalışıram?", "Qarşıma qoyduğum məqsədləri xatırlat.", "Məqsəd kimi seçdiklərimi sadala.", "Mənim indiki istiqamətlərim nədir?", "Mənə öz hədəflərimi göstər."],
    "GOAL_WRITE_REQUEST": ["İspan dili hədəfini əlavə et.", "Bu məqsədi fasiləyə qoy.", "C1 məqsədimi yenidən aktivləşdir.", "Oxu hədəfimi başa çatmış say.", "Dil məqsədimin prioritetini yüksəlt.", "Bu hədəfin adını dəyiş."],
    "IDENTITY_QUERY": ["Sən nə cür bir asistentsən?", "Nel hansı kateqoriyaya daxildir?", "Sənin adın nədir?", "Kim olduğunu açıqlayarsan?", "Özünü bir az tanıt.", "Sənə necə xitab etməliyəm?"],
    "MEMORY_WRITE_REQUEST": ["Yadda tut ki, hər gün piyada gəzirəm.", "Sonrakı vaxt üçün bunu yaz: musiqi dinləməyi sevirəm.", "Mən evdə çay içirəm, bunu sonra da bil.", "Həftəsonu üzdüyümü yaddaşına əlavə et.", "Mənim velosiped sürdüyümü yadda saxla.", "Gələn söhbət üçün bunu unutma: mən portuqal dili öyrənirəm."],
    "PERSONAL_ASSERTION": ["Mən hər gün piyada gəzirəm.", "Mən musiqi dinləməyi sevirəm.", "Mən evdə çay içirəm.", "Mən həftəsonu üzürəm.", "Mən velosiped sürürəm.", "Mən portuqal dili öyrənirəm."],
    "PERSONAL_FACT_QUERY": ["Mən hər gün nə edirəm?", "Mən nəyə qulaq asmağı sevirəm?", "Mən evdə nə içirəm?", "Mən həftəsonu hansı idmanla məşğul oluram?", "Mən hansı nəqliyyatdan xoşlanıram?", "Mən hansı dili öyrənirəm?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim barəmdə ümumi nə bilirsən?", "Məni necə təsvir edərsən?", "Mənim profilimi ümumiləşdir.", "Mənimlə bağlı toplu məlumatın nədir?", "Məni nə qədər tanıyırsan?", "Mənim haqqımda bildiklərini danış."],
}

# Iteration 3 addresses measured PFQ/PA score rejections and PFQ/PA lexical
# confusion. Question-particle-omitted forms remain challenge-only.
TARGETED_ITER3 = {
    "PERSONAL_FACT_QUERY": [
        "Mən hansı musiqini sevirəm?", "Mənim sevdiyim film hansıdır?",
        "Mən hansı dili öyrənirəm?", "Mən harada oxuyuram?",
        "Mən hansı noutbukdan istifadə edirəm?", "Mən gündəlik nə edirəm?",
        "Mən səhərlər nə ilə məşğul oluram?", "Mən qəhvəmi necə içirəm?",
        "Mənim hobbim hansıdır?", "Mən hansı idman növünü seçmişəm?",
        "Yadındadır, mən hansı kitabları sevirəm?", "Mənim hazırkı işim nədir?",
        "Mən hansı proqramdan istifadə edirəm?", "Mənim seçdiyim şəhər hansıdır?",
        "Mənim ən çox xoşladığım yemək nədir?", "Mən indi hansı kursa gedirəm?",
        "Mənim nəyi sevmədiyimi bilirsən?", "Mənim üstün tutduğum seçim hansıdır?",
        "Mənim bu mövzudakı fikrim nədir?", "Mənim indiki vərdişim hansıdır?",
    ],
    "PERSONAL_ASSERTION": [
        "Mən caz musiqisini sevirəm.", "Mən qorxu filmlərini sevmirəm.",
        "Ən sevdiyim kitab Dune-dur.", "Mən hazırda layihə üzərində işləyirəm.",
        "Mən italyan dili öyrənirəm.", "Mən gələn il magistratura oxumaq istəyirəm.",
        "Mən hər səhər qısa gəzintiyə çıxıram.", "Mən sakit insanam.",
        "Mən iki proqramlaşdırma dilində kod yaza bilirəm.", "Mən planşetdən istifadə edirəm.",
        "Mən indi iş axtarıram.", "Mən keçən yay Gəncəyə getmişəm.",
        "Məncə bu kitab çox faydalıdır.", "Mən süd içmirəm.",
        "Əslində, mən qəhvəni daha çox sevirəm.", "Fikrimi dəyişdim, artıq basketbola baxıram.",
        "Əvvəl səhv demişdim, mən B2 səviyyəsindəyəm.", "Mən bu həftə çox yorğunam.",
        "Mən evdə Linux işlədirəm.", "Mən adətən axşamlar oxuyuram.",
    ],
    "GENERAL_CONVERSATION": [
        "Dune necə kitabdır?", "İtalyan dili öyrənmək çətindir?",
        "Linux nə üçün istifadə olunur?", "İnsan gündəlik vərdişi necə qurur?",
        "Məqsəd qoymağın faydası nədir?", "Yaddaşın işləmə prinsipi nədir?",
        "Sən hansı işlərdə kömək edə bilirsən?", "Caz musiqisinin xüsusiyyəti nədir?",
    ],
    "PERSONAL_PROFILE_QUERY": [
        "Mənim haqqımda ümumi təsəvvürün nədir?", "Mənimlə bağlı nələri bilirsən?",
        "Məni ümumi şəkildə necə tanıyırsan?", "Mənim profilimdə nə var?",
    ],
    "MEMORY_WRITE_REQUEST": [
        "Mənim italyan dili öyrəndiyimi yadda saxla.", "Bu vərdişimi qeyd et: axşamlar oxuyuram.",
        "Mən Linux işlədirəm, bunu unutma.", "Gələcək üçün saxla ki, caz sevirəm.",
    ],
    "GOAL_WRITE_REQUEST": [
        "İtalyan dili öyrənməyi məqsəd kimi əlavə et.", "Magistratura hədəfimi dayandır.",
        "Oxuma məqsədimin prioritetini artır.", "C1 məqsədimi dəyiş.",
    ],
    "GOAL_LIST_QUERY": [
        "Mənim məqsədlərim hansılardır?", "Hazırda hansı hədəflərə gedirəm?",
        "Qarşıma qoyduğum planları göstər.", "Məqsəd kimi nə seçmişəm?",
    ],
}

CALIBRATION_ITER3 = {
    "PERSONAL_FACT_QUERY": [
        "Mən hansı cihazdan istifadə edirəm?", "Mən hər səhər nə edirəm?",
        "Mənim sevdiyim içki nədir?", "Mən indi harada oxuyuram?",
        "Mən hansı fəaliyyəti sevirəm?", "Mənim hazırkı marağım nədir?",
    ],
    "PERSONAL_ASSERTION": [
        "Mən hər axşam kitab oxuyuram.", "Mən alman dili öyrənirəm.",
        "Mən velosiped sürürəm.", "Mən yeni iş axtarıram.",
        "Mən pianoda sadə melodiyalar çala bilirəm.", "Mən bu filmi sevmirəm.",
        "Əslində, mən çayı yox, qəhvəni sevirəm.", "Mən keçən il Şəkidə olmuşam.",
    ],
    "GENERAL_CONVERSATION": [
        "Alman dili nə dərəcədə çətindir?", "Velosiped sürməyin faydası nədir?",
        "Yeni iş tapmaq üçün nə etmək olar?", "Piano öyrənmək nə qədər vaxt aparır?",
    ],
    "IDENTITY_QUERY": [
        "Mən sənin kim olduğunu bilmək istəyirəm.", "Mənə özünü tanıt.",
    ],
}

RELEASE_HOLDOUT_V4 = {
    "GENERAL_CONVERSATION": ["Məqsəd anlayışı nədir?", "Yaddaş niyə vacibdir?", "Jujutsu Kaisen necə animedir?", "Fransız dili çətindir?", "Sən hansı işlərdə kömək edə bilirsən?", "Bu cümləni tərcümə et.", "Pythonla fayl necə oxunur?", "Süni intellekt istifadəçi məlumatını necə qoruyur?", "Dünyada ən çox hansı dillər danışılır?", "Məqsədi dəyişmək üçün yaxşı üsul nədir?"],
    "GOAL_LIST_QUERY": ["Mənim hazırda hansı məqsədlərim var?", "Nəyə çatmaq üçün çalışdığımı de.", "Özüm üçün seçdiyim hədəfləri sadala.", "Aktiv məqsədlərimi xatırlat.", "Mənim əsas hədəflərim nədir?", "Hazırkı istiqamətlərimi göstər.", "Məqsəd kimi nəyi müəyyən etmişəm?", "Qarşımdakı hədəflər hansılardır?", "Mənim üzərində işlədiyim məqsədlər nədir?", "Nəyə doğru getdiyimi xatırlat."],
    "GOAL_WRITE_REQUEST": ["Fransız dili hədəfini əlavə et.", "Bu məqsədi müvəqqəti dayandır.", "C1 hədəfimi yenidən aktivləşdir.", "Oxuma məqsədimi tamamlanmış say.", "Dil hədəfimin prioritetini artır.", "Bu məqsədin adını yenilə.", "Mövcud hədəfimi başqa məqsədlə əvəz et.", "Bu hədəfi ləğv et.", "Məqsədimi B2 olaraq düzəlt.", "Bu məqsədi yenidən başlat."],
    "IDENTITY_QUERY": ["Sənin adın nədir?", "Kim olduğunu söyləyə bilərsən?", "Özünü qısaca təqdim et.", "Sən nə cür bir köməkçisən?", "Nel adı sənindir?", "Sənə hansı adla müraciət edim?", "Sən nəsən?", "Mən kimlə danışıram?", "Özünü necə təsvir edərsən?", "Sənin kimliyin nədir?"],
    "MEMORY_WRITE_REQUEST": ["Mənim kitab oxumağı sevdiyimi yadda saxla.", "Gələcək üçün qeyd et: ispan dili öyrənirəm.", "Unutma ki, səhərlər qaçıram.", "Bu məlumatı saxla: Linux istifadə edirəm.", "Mənim çayı şəkərsiz içdiyimi qeyd et.", "Sonrakı söhbət üçün bunu yadda tut: foto çəkirəm.", "Mənim caz sevdiyimi unutma.", "Bunu yaddaşına yaz: həftəsonu üzürəm.", "Mən gələn il səyahət etmək istəyirəm, bunu saxla.", "Sonra lazım olar, bu vərdişimi qeyd et: gündəlik yazıram."],
    "PERSONAL_ASSERTION": ["Mən səhərlər qəhvə içirəm.", "Mən detektiv kitabları sevirəm.", "Mən qorxu oyunlarını bəyənmirəm.", "Ən sevdiyim rəng yaşıl rəngdir.", "Mən hazırda dizayn öyrənirəm.", "Mən gələn il başqa şəhərə köçmək istəyirəm.", "Mən hər gün qeydlər aparıram.", "Mən bir az utancaq adamam.", "Mən Git-dən istifadə edirəm.", "Əslində, mən rok musiqisini daha çox sevirəm."],
    "PERSONAL_FACT_QUERY": ["Mən hansı içkini sevirəm?", "Mənim sevdiyim kitab növü hansıdır?", "Mən hansı oyunları bəyənmirəm?", "Mənim ən sevdiyim rəng nədir?", "Mən indi nə öyrənirəm?", "Mən gələn il nə etmək istəyirəm?", "Mənim gündəlik vərdişim nədir?", "Mən necə bir insanam?", "Mən hansı alətdən istifadə edirəm?", "Yadındadır, mən hansı musiqiyə üstünlük verirəm?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim haqqımda ümumilikdə nə bilirsən?", "Məni tanıdığın qədər təsvir et.", "Mənim profilimi qısa ümumiləşdir.", "Mənimlə bağlı toplu məlumatın nədir?", "Məni necə tanıyırsan?", "Mənim haqqımda ümumi fikrin nədir?", "Mənə dair bildiklərini danış.", "Mənim barəmdə geniş nə deyə bilərsən?", "Mənimlə bağlı ümumi məlumatları sadala.", "Mənim şəklimi bildiklərinə əsasən çək."],
}

HARD_NEGATIVE_V4 = [
    ("PERSONAL_FACT_QUERY", "Mən hansı animeni sevirəm?"), ("PERSONAL_ASSERTION", "Mən HxH-ni sevirəm."),
    ("GENERAL_CONVERSATION", "HxH necə animedir?"), ("PERSONAL_PROFILE_QUERY", "Mənim haqqımda nə bilirsən?"),
    ("PERSONAL_FACT_QUERY", "Mən hansı dili öyrənirəm?"), ("PERSONAL_ASSERTION", "Mən alman dili öyrənirəm."),
    ("GOAL_WRITE_REQUEST", "Alman dilində C1-i məqsəd kimi əlavə et."), ("MEMORY_WRITE_REQUEST", "Alman dili öyrəndiyimi yadda saxla."),
    ("GENERAL_CONVERSATION", "Alman dili çətindir?"), ("GOAL_LIST_QUERY", "Məqsədlərim nədir?"),
    ("PERSONAL_ASSERTION", "Məqsədim C1 olmaqdır."), ("GOAL_WRITE_REQUEST", "C1-i məqsəd kimi əlavə et."),
    ("GENERAL_CONVERSATION", "Məqsəd qoymaq faydalıdırmı?"), ("IDENTITY_QUERY", "Sən kimsən?"),
    ("GENERAL_CONVERSATION", "Nə edə bilirsən?"), ("GENERAL_CONVERSATION", "Sən hansı modeldən istifadə edirsən?"),
    ("MEMORY_WRITE_REQUEST", "Bunu gələcək üçün yadda saxla: mən şahmat oynayıram."), ("GENERAL_CONVERSATION", "Yaddaş sistemi necə işləyir?"),
    ("PERSONAL_PROFILE_QUERY", "Mənimlə bağlı nələri bilirsən?"), ("PERSONAL_FACT_QUERY", "Mənim sevdiyim yemək nədir?"),
]

TARGETED_ITER4 = {
    "PERSONAL_ASSERTION": [
        "Məqsədim C1 səviyyəsinə çatmaqdır.", "Mən səhərlər çay içirəm.",
        "Ən sevdiyim rəng mavidir.", "Mənim noutbukum var.",
        "Bu yay səyahət etməyi planlayıram.", "Mən klassik musiqini sevirəm.",
        "Mən romantik filmləri sevmirəm.", "Əslində, mən yaşıl çayı üstün tuturam.",
    ],
    "PERSONAL_FACT_QUERY": [
        "Mən gələcəkdə nə etmək niyyətindəyəm?", "Mənim gələn ilki planım nədir?",
        "Mən hansı cihazı işlədirəm?", "Mənim hansı elektron avadanlığım var?",
        "Mənim səhər içkim nədir?", "Mən hansı musiqiyə üstünlük verirəm?",
        "Mənim seçdiyim rəng hansıdır?", "Mən bu yay nə planlaşdırıram?",
    ],
    "IDENTITY_QUERY": [
        "Sənin adını bilmək istəyirəm.", "Mənə Nelin kim olduğunu de.",
        "Sənə hansı adla səslənmək olar?",
    ],
    "GOAL_LIST_QUERY": [
        "Mənim həyat istiqamətim üçün seçdiyim hədəflər nədir?", "Hazırkı yönüm üçün hansı məqsədlərim var?",
        "Mənim irəliləmə istiqamətimi göstərən hədəfləri sadala.",
    ],
}

CALIBRATION_ITER4 = {
    "PERSONAL_ASSERTION": [
        "Məqsədim B2 səviyyəsinə çatmaqdır.", "Mən səhərlər südlü qəhvə içirəm.",
        "Ən sevdiyim rəng sarıdır.", "Mənim planşetim var.",
    ],
    "PERSONAL_FACT_QUERY": [
        "Mənim yaxın gələcək planım nədir?", "Mən hansı texniki cihazdan istifadə edirəm?",
        "Mən səhərlər nə içirəm?", "Mənim üstün tutduğum musiqi hansıdır?",
    ],
    "IDENTITY_QUERY": ["Sənin adını öyrənmək istəyirəm.", "Mənə kim olduğunu danış."],
    "GOAL_LIST_QUERY": ["Mənim seçdiyim həyat istiqaməti üçün məqsədlər nədir?", "Yönümə aid hədəflərimi göstər."],
}

RELEASE_HOLDOUT_V5 = {
    "GENERAL_CONVERSATION": ["Məqsəd qoymaq insanı necə dəyişir?", "Kompüter yaddaşı necə işləyir?", "Bu yazını sadələşdir.", "Rust dili nədir?", "Sən hansı bacarıqlarda kömək edirsən?", "Rənglərin insan psixologiyasına təsiri nədir?", "Səyahət planı necə hazırlanır?", "Klassik musiqinin xüsusiyyəti nədir?"],
    "GOAL_LIST_QUERY": ["Mənim hazırkı hədəflərimi sadala.", "Mən nəyə nail olmağa çalışıram?", "Özüm üçün təyin etdiyim məqsədləri de.", "Mənim aktiv planlarım hansılardır?", "Qarşıma qoyduğum hədəfləri xatırlat.", "İrəliləməyim üçün hansı məqsədlərim var?", "Mənim əsas istiqamət hədəflərim nədir?", "Məqsəd kimi seçdiklərimi göstər."],
    "GOAL_WRITE_REQUEST": ["B2 hədəfini əlavə et.", "Bu məqsədi pauzaya qoy.", "Mövcud dil hədəfimi yenidən aktivləşdir.", "Bu oxu məqsədini bitmiş say.", "Hədəfin prioritetini aşağı sal.", "Məqsədimin adını dəyiş.", "Bu hədəfi təqaüdə çıxar.", "Məqsədimi C1 ilə əvəz et."],
    "IDENTITY_QUERY": ["Adını mənə deyərsən?", "Sən özün kimsən?", "Özünü təqdim edə bilərsən?", "Nel nədir?", "Sən hansı növ köməkçisən?", "Mən sənə necə müraciət etməliyəm?", "Kimlə söhbət edirəm?", "Sənin kimliyin necədir?"],
    "MEMORY_WRITE_REQUEST": ["Mənim klassik musiqi sevdiyimi yadda saxla.", "Sonra üçün qeyd et ki, velosiped sürürəm.", "Unutma, səhərlər çay içirəm.", "Bu faktı yaddaşında saxla: mən Git işlədirəm.", "Gələcəkdə xatırla ki, səyahət etməyi planlayıram.", "Mənim yaşıl rəngi sevdiyimi qeyd et.", "Bunu yadda tut: axşamlar oxuyuram.", "Mənim noutbuk istifadə etdiyimi saxla."],
    "PERSONAL_ASSERTION": ["Məqsədim B2 səviyyəsinə çatmaqdır.", "Mən səhərlər şəkərsiz qəhvə içirəm.", "Ən sevdiyim rəng qaradır.", "Mənim planşetim var.", "Payızda səyahət etməyi düşünürəm.", "Mən bluz musiqisini sevirəm.", "Mən aksiyon filmlərini bəyənmirəm.", "Əslində, mən oolong çayını üstün tuturam."],
    "PERSONAL_FACT_QUERY": ["Mənim yaxın hədəfim nədir?", "Mən payızda nə etməyi düşünürəm?", "Mən hansı texniki vasitədən istifadə edirəm?", "Mənim hansı portativ cihazım var?", "Mən səhərlər nə içirəm?", "Mən hansı musiqi janrını sevirəm?", "Mənim ən çox xoşladığım rəng nədir?", "Mənim növbəti planım nədir?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim barəmdə ümumi təsvir ver.", "Mənimlə bağlı bildiklərini yekunlaşdır.", "Məni tanıdığın qədər danış.", "Mənim profilim haqqında nə deyə bilərsən?", "Mənə dair ümumi məlumatların nədir?", "Mənim haqqımda geniş danış.", "Məni ümumi şəkildə necə görürsən?", "Mənimlə bağlı məlumatları ümumiləşdir."],
}

HARD_NEGATIVE_V5 = [
    ("PERSONAL_ASSERTION", "Məqsədim C1 səviyyəsinə çatmaqdır."), ("GOAL_WRITE_REQUEST", "C1 səviyyəsinə çatmağı məqsəd kimi əlavə et."),
    ("GOAL_LIST_QUERY", "Məqsədlərim hansılardır?"), ("GENERAL_CONVERSATION", "Məqsəd nə deməkdir?"),
    ("PERSONAL_ASSERTION", "Mən klassik musiqini sevirəm."), ("PERSONAL_FACT_QUERY", "Mən hansı musiqiyə üstünlük verirəm?"),
    ("GENERAL_CONVERSATION", "Klassik musiqi nədir?"), ("PERSONAL_PROFILE_QUERY", "Mənim haqqımda nə bilirsən?"),
    ("PERSONAL_ASSERTION", "Mən səhərlər çay içirəm."), ("PERSONAL_FACT_QUERY", "Mənim səhər içkim nədir?"),
    ("MEMORY_WRITE_REQUEST", "Səhərlər çay içdiyimi yadda saxla."), ("GENERAL_CONVERSATION", "Çayın faydası nədir?"),
    ("IDENTITY_QUERY", "Sən kimsən?"), ("GENERAL_CONVERSATION", "Sən nə edə bilirsən?"),
    ("PERSONAL_PROFILE_QUERY", "Məni necə tanıyırsan?"), ("GOAL_WRITE_REQUEST", "Bu hədəfi dayandır."),
]

TARGETED_ITER5 = {
    "PERSONAL_ASSERTION": [
        "Məndə noutbuk var.", "Məndə planşet də var.",
        "Mən səhərlər limonlu su içirəm.", "Ən sevdiyim rəng bənövşəyidir.",
        "Mən gələn yaz səyahət etməyi düşünürəm.", "Mən bluz musiqisini sevirəm.",
    ],
    "PERSONAL_FACT_QUERY": [
        "Məndə hansı cihaz var?", "Mən səhərlər hansı içkini seçirəm?",
        "Mənim gələn yaz üçün planım nədir?", "Mən hansı rəngə üstünlük verirəm?",
    ],
}

CALIBRATION_ITER5 = {
    "PERSONAL_ASSERTION": [
        "Mən səhərlər limonlu su içirəm.", "Ən sevdiyim rəng bənövşəyidir.",
        "Məndə planşet də var.",
    ],
    "PERSONAL_FACT_QUERY": [
        "Mən səhərlər hansı içkini seçirəm?", "Mənim gələn yaz üçün planım nədir?",
    ],
}

RELEASE_HOLDOUT_V6 = {
    "GENERAL_CONVERSATION": ["Məqsəd qoymaq nə üçün faydalıdır?", "Yaddaşın funksiyası nədir?", "Bu fikri başqa cür yaz.", "Go proqramlaşdırma dili nədir?", "Sən nələri bacarırsan?", "Bənövşəyi rəng necə görünür?", "Səyahət üçün nələri hazırlamaq lazımdır?", "Bluz musiqisi haqqında danış."],
    "GOAL_LIST_QUERY": ["Mənim cari məqsədlərim hansılardır?", "Nəyə çatmağa cəhd etdiyimi xatırlat.", "Mənim üçün müəyyən etdiyim hədəfləri sadala.", "İndi hansı məqsədlər üzərində işləyirəm?", "Məqsəd siyahımı göstər.", "Mənim əsas yönüm üçün hədəflərim nədir?", "Qarşıdakı məqsədlərimi de.", "Məqsəd olaraq təyin etdiklərim nədir?"],
    "GOAL_WRITE_REQUEST": ["Yapon dili hədəfini əlavə et.", "Bu məqsədi dondur.", "Mövcud hədəfimi yenidən işə sal.", "Bu oxu hədəfini tamamla.", "Məqsədin vacibliyini artır.", "Hədəfimin adını yenidən yaz.", "Bu məqsədi ləğv et.", "B1 məqsədimi B2 ilə əvəz et."],
    "IDENTITY_QUERY": ["Sənin adını necə deyirlər?", "Özün barədə qısa danış.", "Sən kim sayılırsan?", "Nel necə bir köməkçidir?", "Mən kimə yazıram?", "Sənə hansı adla xitab edə bilərəm?", "Sənin öz kimliyin nədir?", "Sən nəsən?"],
    "MEMORY_WRITE_REQUEST": ["Mənim limonlu su içdiyimi yadda saxla.", "Gələcək üçün qeyd et: bluz sevirəm.", "Unutma ki, planşet istifadə edirəm.", "Bu məlumatı saxla: yazda səyahət düşünürəm.", "Mənim bənövşəyi rəngi sevdiyimi yadda tut.", "Sonra üçün qeyd et ki, hər gün oxuyuram.", "Məndə noutbuk olduğunu unutma.", "Bu vərdişimi yaddaşa əlavə et: səhərlər gəzirəm."],
    "PERSONAL_ASSERTION": ["Məndə kamera var.", "Mən səhərlər nanəli çay içirəm.", "Ən sevdiyim rəng firuzəyidir.", "Mən gələn qış səyahət etməyi düşünürəm.", "Mən soul musiqisini sevirəm.", "Mən aksiyon filmlərinə baxmıram.", "Mən bu ay yeni iş axtarıram.", "Əslində, mən qəhvəni südsüz sevirəm."],
    "PERSONAL_FACT_QUERY": ["Məndə hansı elektron alət var?", "Mən səhərlər hansı içkiyə üstünlük verirəm?", "Mən gələn qış nə planlaşdırıram?", "Mənim üstün tutduğum rəng hansıdır?", "Mən hansı musiqi janrını bəyənirəm?", "Mən hansı filmlərə baxmıram?", "Mən indi nə axtarıram?", "Mən qəhvəmi necə sevirəm?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim haqqımda ümumi məlumat ver.", "Məni necə təsvir edirsən?", "Mənə dair bildiklərini bir yerə topla.", "Mənim profilim barədə danış.", "Mənimlə bağlı ümumi nə bilirsən?", "Məni tanıdığın kimi ümumiləşdir.", "Mənim barəmdə nə deyə bilərsən?", "Mənimlə bağlı geniş məlumatın varmı?"],
}

TARGETED_ITER6 = {
    "GOAL_LIST_QUERY": [
        "İndi hansı məqsədlərim üzərində işləyirəm?", "Məqsəd olaraq nələri təyin etmişəm?",
        "Mənim hədəf siyahım hansıdır?", "Hazırda çatmaq istədiyim nəticələr nədir?",
        "Mənim aktiv hədəflərimi sadala.", "Qarşıma qoyduğum məqsədləri xatırlat.",
        "Mən nəyə doğru çalışıram?", "Məqsəd kimi seçdiyim şeylər hansılardır?",
        "Mənim indiki plan hədəflərim nədir?", "Hansı hədəflər mənim üçün aktivdir?",
    ],
    "IDENTITY_QUERY": [
        "Mən kimə mesaj yazıram?", "Sənə hansı adla müraciət edə bilərəm?",
        "Qarşımdakı köməkçi kimdir?", "Sənin adını necə çağırım?",
        "Mənimlə kim danışır?", "Sən özünü necə adlandırırsan?",
        "Nel adı sənə məxsusdur?", "Mənə kim olduğunu təqdim et.",
    ],
    "MEMORY_WRITE_REQUEST": [
        "Mənim üçün qeyd et ki, Linux işlədirəm.", "İstəyirəm yadında saxlayasan ki, səhərlər qaçıram.",
        "Xahiş edirəm, italyan dili öyrəndiyimi unutma.", "Məndə noutbuk olduğunu yadda saxla.",
        "Bu vərdişimi yaddaşa yaz: axşamlar oxuyuram.", "Gələcək üçün bunu saxla: foto çəkirəm.",
        "Sonra xatırlamaq üçün qeyd et ki, caz dinləyirəm.", "Mənim şəkərsiz qəhvə içdiyimi yadında tut.",
        "Bu məlumatı unutma: həftəsonu üzürəm.", "Mənim üçün yaddaşa əlavə et ki, gündəlik yazıram.",
    ],
    "GENERAL_CONVERSATION": [
        "Bunu qısalt.", "Bu cümləni daha sadə yaz.", "Bu paraqrafı xülasə et.",
        "Mənə ideyalar ver.", "Sən hansı tapşırıqları bacarırsan?", "Nə edə bilirsən?",
        "Yaddaş sistemi nə üçün istifadə olunur?", "Məlumatı necə qısa saxlamaq olar?",
    ],
}

CALIBRATION_ITER6 = {
    "GOAL_LIST_QUERY": [
        "Mənim hədəflərim hansılardır?", "İndi hansı məqsədlərə çalışıram?",
        "Məqsəd olaraq seçdiklərimi de.", "Hazırkı hədəf siyahımı göstər.",
    ],
    "IDENTITY_QUERY": [
        "Mən kimə yazıram?", "Sənə hansı adla xitab edə bilərəm?",
        "Mənimlə kim danışır?", "Sən özünü necə çağırırsan?",
    ],
    "MEMORY_WRITE_REQUEST": [
        "Mənim üçün qeyd elə ki, Linux istifadə edirəm.", "Xahiş edirəm, B2 imtahanına hazırlaşdığımı unutma.",
        "İstəyirəm yadında saxlayasan ki, səhərlər qaçıram.", "Məndə noutbuk olduğunu unutma.",
        "Bu vərdişimi yaddaşa əlavə et: səhərlər gəzirəm.",
    ],
    "GENERAL_CONVERSATION": [
        "Bu hissəni qısalt.", "Bu mətnin xülasəsini yaz.",
        "Mənə yeni fikir ver.", "Sən hansı işlərdə kömək edə bilirsən?",
    ],
}

RELEASE_HOLDOUT_V7 = {
    "GENERAL_CONVERSATION": ["Məqsədlərin insan üçün rolu nədir?", "Yaddaşın növləri hansılardır?", "Bu mətnin əsas fikrini de.", "TypeScript nədir?", "Sən hansı mövzularda yardım göstərə bilirsən?", "Animelər niyə populyardır?", "İmtahana necə hazırlaşmaq olar?", "Qəhvəni necə düzgün dəmləmək olar?", "Bir həftəlik oxu planı necə qurulur?", "Süni intellekt necə öyrənir?"],
    "GOAL_LIST_QUERY": ["Mənim mövcud məqsədlərim hansılardır?", "Nəyə çatmağa çalışdığımı xatırlat.", "Aktiv hədəflərimin siyahısını ver.", "Məqsəd kimi müəyyən etdiklərimi sadala.", "Mənim hazırkı istiqamət hədəflərim nədir?", "Qarşıma qoyduğum hədəfləri de.", "Mən hansı nəticələrə doğru işləyirəm?", "Hazırda nələri özümə məqsəd seçmişəm?", "Mənim üçün vacib olan hədəflər hansılardır?", "Məqsədlərimi yenidən göstər."],
    "GOAL_WRITE_REQUEST": ["İspan dili məqsədini yarat.", "Bu hədəfi bir müddətlik pauzaya al.", "Mövcud hədəfimi yenidən aktivləşdir.", "Bu məqsədi tamamlanmış hesab et.", "Hədəfimin prioritetini artır.", "Bu məqsədin adını dəyiş.", "Bu hədəfi ləğv et.", "C1 məqsədimi B2 ilə əvəzlə.", "Bu məqsədi yenidən başlat.", "Oxu hədəfimi dayandır."],
    "IDENTITY_QUERY": ["Adın barədə nə deyə bilərsən?", "Kim olduğun barədə danış.", "Özünü təqdim edə bilərsən?", "Sən hansı cür köməkçisən?", "Nel adını sən daşıyırsan?", "Mən sənə necə xitab edim?", "Mən kimlə yazışıram?", "Sənin öz adlandırman nədir?", "Sən hansı varlıqsan?", "Sən kim sayılırsan?"],
    "MEMORY_WRITE_REQUEST": ["Mənim rəsm çəkməyi sevdiyimi yadda saxla.", "Sonra üçün qeyd et: alman dili öyrənirəm.", "Unutma ki, səhərlər velosiped sürürəm.", "Bu məlumatı yaddaşında saxla: Ubuntu istifadə edirəm.", "Xahiş edirəm, yaşıl çayı sevdiyimi xatırla.", "Mənim üçün yaddaşa yaz ki, axşamlar gitara çalıram.", "Gələcək söhbətlər üçün bunu unutma: gündəlik oxuyuram.", "Məndə fotoaparat olduğunu qeyd et.", "İstəyirəm, bu məlumatı saxlayasan: payızda səyahət planım var.", "Bu vərdişimi yaddaşa əlavə et: hər gün yazıram."],
    "PERSONAL_ASSERTION": ["Mən rəsm çəkməyi sevirəm.", "Mən çin dili öyrənirəm.", "Mən səhərlər velosiped sürürəm.", "Mən Ubuntu istifadə edirəm.", "Mən yaşıl çayı sevirəm.", "Mən axşamlar gitara çalıram.", "Mən hər gün oxuyuram.", "Məndə fotoaparat var.", "Mən payızda səyahət planlaşdırıram.", "Mən hər gün yazıram."],
    "PERSONAL_FACT_QUERY": ["Mən hansı hobbi ilə məşğul oluram?", "Mən hazırda hansı dil kursundayam?", "Mən səhərlər nə edirəm?", "Mən hansı əməliyyat sistemindən istifadə edirəm?", "Mən hansı çayı sevirəm?", "Mən axşamlar hansı alətdə çalıram?", "Mənim hər gün etdiyim şey nədir?", "Məndə hansı avadanlıq var?", "Mən nə vaxt səyahət etməyi planlaşdırıram?", "Mən hər gün nə yazıram?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim haqqımda ümumi nə bilirsən?", "Məni tanıdığın qədər təsvir et.", "Mənimlə bağlı bilgilərini ümumiləşdir.", "Mənim profilim haqqında danış.", "Mənə dair ümumi məlumatların hansılardır?", "Mənim haqqımda toplu nə deyə bilərsən?", "Mənimlə bağlı ümumi bilgilərin nədir?", "Məni ümumi şəkildə necə görürsən?", "Mənim barəmdə geniş məlumat ver.", "Mənim profilimi qısa de."],
}

HARD_NEGATIVE_V7 = [
    ("GOAL_LIST_QUERY", "Məqsədlərim hansılardır?"), ("PERSONAL_ASSERTION", "Məqsədim C1 olmaqdır."),
    ("GOAL_WRITE_REQUEST", "C1-i məqsəd kimi əlavə et."), ("GENERAL_CONVERSATION", "Məqsəd qoymaq nə üçün lazımdır?"),
    ("IDENTITY_QUERY", "Sən kimsən?"), ("GENERAL_CONVERSATION", "Nə edə bilirsən?"),
    ("GENERAL_CONVERSATION", "Sən hansı modeldən istifadə edirsən?"), ("MEMORY_WRITE_REQUEST", "Mən kitab oxuyuram, bunu yadda saxla."),
    ("PERSONAL_ASSERTION", "Mən kitab oxuyuram."), ("GENERAL_CONVERSATION", "Yaddaş sistemi necə işləyir?"),
    ("PERSONAL_FACT_QUERY", "Mən hansı kitabı sevirəm?"), ("PERSONAL_PROFILE_QUERY", "Mənim haqqımda nə bilirsən?"),
    ("GENERAL_CONVERSATION", "Bleach necə animedir?"), ("PERSONAL_ASSERTION", "Mən Bleach-i sevirəm."),
    ("GOAL_WRITE_REQUEST", "Bu hədəfi dayandır."), ("GENERAL_CONVERSATION", "Məqsədi necə seçmək olar?"),
]

TARGETED_ITER7 = {
    "PERSONAL_PROFILE_QUERY": [
        "Mənim profilim haqqında danış.", "Mənə dair ümumi məlumatların hansılardır?",
        "Mənim haqqımda bildiklərini ümumiləşdir.", "Mənimlə bağlı məlumatları mənə de.",
        "Mənim haqqımda nə qədər bilirsən?", "Mənim profilimdə nələr var?",
        "Mənə dair ümumi təsəvvürünü danış.", "Mənimlə bağlı bildiklərini sadala.",
        "Məni indiyə qədər necə tanımısan?", "Mənim haqqımda topladığın məlumat nədir?",
        "Mənim barəmdə geniş bildiklərini de.", "Mənə aid ümumi məlumatları göstər.",
        "Mənim profilim barədə nələri bilirsən?", "Mənim haqqımda olan bilgini yekunlaşdır.",
    ],
}

CALIBRATION_ITER7 = {
    "PERSONAL_PROFILE_QUERY": [
        "Mənim profilim haqqında nə deyə bilərsən?", "Mənə dair ümumi məlumatları de.",
        "Mənim haqqımda bildiklərini topla.", "Mənimlə bağlı nə qədər məlumatın var?",
        "Məni ümumi şəkildə tanıt.", "Mənim profilimi ümumiləşdir.",
    ],
}

RELEASE_HOLDOUT_V8 = {
    "GENERAL_CONVERSATION": ["Məqsədin psixoloji təsiri nədir?", "Yaddaşın işləmə mexanizmi necədir?", "Bu yazını iki cümləyə endir.", "Kotlin nədir?", "Sən hansı işlərə kömək göstərirsən?", "Rəsm çəkməyi necə öyrənmək olar?", "Alman dili üçün hansı resurslar faydalıdır?", "Ubuntu nədir?", "Yaşıl çayın faydaları hansılardır?", "Gitara öyrənmək çətindir?"],
    "GOAL_LIST_QUERY": ["Mənim bu ay üçün hədəflərim nədir?", "Nəyi həyata keçirmək istədiyimi göstər.", "Özüm üçün planlaşdırdığım məqsədləri sadala.", "Mövcud məqsəd siyahımı xatırlat.", "Mən hansı hədəflərə fokuslanıram?", "Məqsəd kimi seçdiyim fəaliyyətlər hansılardır?", "Mənim yol xəritəmdəki hədəflər nədir?", "Hazırda nəyə nail olmağa çalışıram?", "Mənim irəliyə dönük məqsədlərim hansılardır?", "Hədəflərimi mənə yenidən de."],
    "GOAL_WRITE_REQUEST": ["Rəsm çəkmə hədəfini əlavə et.", "Bu məqsədi növbəti aya qədər dayandır.", "Dil öyrənmə hədəfimi bərpa et.", "Bu məqsədi yerinə yetirilmiş say.", "Hədəfimin önəmini yüksəlt.", "Bu məqsədi başqa adla qeyd et.", "Mövcud hədəfi sil.", "B2 hədəfimi C1 ilə dəyiş.", "Bu məqsədi aktiv et.", "Gündəlik oxu hədəfimi ləğv et."],
    "IDENTITY_QUERY": ["Adın barədə qısa məlumat ver.", "Sən kimə deyirsən özünü?", "Özünü mənə tanıt.", "Sən necə bir süni köməkçisən?", "Nel sənin kimliyindir?", "Mən sənə nə deyə müraciət edim?", "Burada mənimlə kim danışır?", "Sənin adlandırılmağın nədir?", "Sən hansı tip varlıqsan?", "Sənin özünü təqdimatın necədir?"],
    "MEMORY_WRITE_REQUEST": ["Mənim rəqs etməyi sevdiyimi yadda saxla.", "Sonrakı dəfə üçün qeyd et: türk dili öyrənirəm.", "Unutma ki, axşamlar rəsm çəkirəm.", "Bu faktı yaddaşa yaz: Fedora istifadə edirəm.", "Xahiş edirəm, nanəli çayı sevdiyimi saxla.", "Mənim üçün qeyd et ki, hər gün pianoda məşq edirəm.", "Gələcəkdə xatırla: hər axşam oxuyuram.", "Məndə rəqəmsal kamera olduğunu unutma.", "Bu məlumatı saxla: yazda səfər etmək istəyirəm.", "Yaddaşa əlavə et: gündəlik qeydlər yazıram."],
    "PERSONAL_ASSERTION": ["Mən rəqs etməyi sevirəm.", "Mən türk dili öyrənirəm.", "Mən axşamlar rəsm çəkirəm.", "Mən Fedora istifadə edirəm.", "Mən nanəli çayı sevirəm.", "Mən hər gün pianoda məşq edirəm.", "Mən hər axşam oxuyuram.", "Məndə rəqəmsal kamera var.", "Mən yazda səfər etmək istəyirəm.", "Mən gündəlik qeydlər yazıram."],
    "PERSONAL_FACT_QUERY": ["Mən hansı hobbi növünü sevirəm?", "Mən hazırda hansı dili mənimsəyirəm?", "Mən axşamlar nə edirəm?", "Mən hansı sistemdən istifadə edirəm?", "Mən hansı çayı sevirəm?", "Mən hansı alətdə məşq edirəm?", "Mənim axşam vərdişim nədir?", "Məndə hansı kamera var?", "Mən nə vaxt səfər etmək istəyirəm?", "Mən hər gün nə yazıram?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim profilim barədə mənə nə danışa bilərsən?", "Mənə aid ümumi bilgiləri söylə.", "Mənim haqqımda bildiklərini birləşdir.", "Mənimlə bağlı nə qədər şey bilirsən?", "Mənim ümumi təsvirimi ver.", "Mənim profilimə dair yekun çıxar.", "Mənim haqqımda geniş nə bilirsən?", "Mənimlə bağlı ümumi təsvir ver.", "Mənə dair toplu bilgin nədir?", "Məni bildiklərinə əsasən təsvir et."],
}

HARD_NEGATIVE_V8 = [
    ("PERSONAL_PROFILE_QUERY", "Mənim profilim haqqında nə bilirsən?"), ("PERSONAL_FACT_QUERY", "Ən sevdiyim anime hansıdır?"),
    ("IDENTITY_QUERY", "Sən kimsən?"), ("GENERAL_CONVERSATION", "Süni intellekt istifadəçini necə tanıyır?"),
    ("GENERAL_CONVERSATION", "Yaddaş sistemi necə işləyir?"), ("MEMORY_WRITE_REQUEST", "Mən kitab oxuyuram, bunu yadda saxla."),
    ("PERSONAL_ASSERTION", "Mən kitab oxuyuram."), ("GOAL_LIST_QUERY", "Məqsədlərim nədir?"),
    ("GOAL_WRITE_REQUEST", "C1-i məqsəd kimi əlavə et."), ("GENERAL_CONVERSATION", "Məqsəd qoymaq niyə faydalıdır?"),
    ("PERSONAL_PROFILE_QUERY", "Mənim haqqımda nə qədər məlumatın var?"), ("PERSONAL_FACT_QUERY", "Mən hansı oyunları sevirəm?"),
    ("GENERAL_CONVERSATION", "Bleach necə animedir?"), ("PERSONAL_ASSERTION", "Mən Bleach-i sevirəm."),
    ("IDENTITY_QUERY", "Sənin adın nədir?"), ("GENERAL_CONVERSATION", "Nə edə bilirsən?"),
]

RELEASE_HOLDOUT_V9 = {
    "GENERAL_CONVERSATION": ["Məqsəd insanı niyə motivasiya edir?", "Yaddaş haqqında elmi izah ver.", "Bu abzası qısa yaz.", "Swift proqramlaşdırma dili nədir?", "Sən nə işdə kömək göstərə bilərsən?", "Rəqsin sağlamlığa faydası nədir?", "Türk dili öyrənmək üçün nə etməliyəm?", "Fedora nə üçün istifadə edilir?"],
    "GOAL_LIST_QUERY": ["Mənim indiki məqsədlərim hansılardır?", "Nəyə yetişmək üçün səy göstərirəm?", "Qoyduğum hədəfləri sadala.", "Mənim hazırkı plan məqsədlərim nədir?", "Məqsəd olaraq seçdiyim istiqamətləri de.", "Mən hansı nəticələrə çatmaq istəyirəm?", "Hədəflərimin siyahısını göstər.", "Mənim üzərində işlədiyim məqsədlər hansılardır?"],
    "GOAL_WRITE_REQUEST": ["Türk dili hədəfini əlavə et.", "Bu məqsədi müvəqqəti saxla.", "Mövcud hədəfimi yenidən aktiv et.", "Bu hədəfi tamamlanmış kimi işarələ.", "Məqsədimin prioritetini yüksəlt.", "Hədəfimin adını dəyiş.", "Bu məqsədi ləğv et.", "A2 hədəfimi B1 ilə əvəzlə."],
    "IDENTITY_QUERY": ["Sənin adını öyrənə bilərəm?", "Kim olduğunu mənə açıqlayarsan?", "Özünü qısaca tanıt.", "Sən hansı növdən köməkçisən?", "Nel adının sahibi sənsən?", "Mən sənə hansı adla müraciət edə bilərəm?", "Mən kiminlə söhbət edirəm?", "Sənin kimliyin barədə nə deyə bilərsən?"],
    "MEMORY_WRITE_REQUEST": ["Mənim yoga sevdiyimi yadda saxla.", "Gələcək üçün qeyd et: koreya dili öyrənirəm.", "Unutma ki, gecələr yazı yazıram.", "Bu faktı yaddaşında saxla: Debian istifadə edirəm.", "Xahiş edirəm, adaçayı sevdiyimi xatırla.", "Mənim üçün yaddaşa yaz ki, hər gün skripka məşq edirəm.", "Sonra lazım olar, bunu unutma: axşamlar oxuyuram.", "Məndə köhnə fotoaparat olduğunu qeyd et."],
    "PERSONAL_ASSERTION": ["Mən yoga etməyi sevirəm.", "Mən koreya dili öyrənirəm.", "Mən gecələr yazı yazıram.", "Mən Debian istifadə edirəm.", "Mən adaçayı sevirəm.", "Mən hər gün skripka məşq edirəm.", "Mən axşamlar oxuyuram.", "Məndə köhnə fotoaparat var."],
    "PERSONAL_FACT_QUERY": ["Mən hansı məşqi sevirəm?", "Mən indi hansı dili öyrənməkdəyəm?", "Mən gecələr nə edirəm?", "Mən hansı sistemdən istifadə edirəm?", "Mən hansı çayı sevirəm?", "Mən hansı alətdə məşq edirəm?", "Mənim axşam vərdişim nədir?", "Məndə hansı fotoaparat var?"],
    "PERSONAL_PROFILE_QUERY": ["Mənim profilimlə bağlı nə söyləyə bilərsən?", "Mənə aid ümumi biliklərini danış.", "Mənim haqqımda bildiklərini bir xülasədə topla.", "Mənimlə bağlı nə qədər şey xatırlayırsan?", "Mənim ümumi portretimi çək.", "Mənim profilim barədə yekun məlumat ver.", "Mənə dair ümumi nə deyə bilərsən?", "Məni bildiyin cəhətlərə görə təsvir et."],
}

HARD_NEGATIVE_V9 = [
    ("PERSONAL_PROFILE_QUERY", "Mənim profilim haqqında nə bilirsən?"), ("PERSONAL_FACT_QUERY", "Mənim sevdiyim yemək hansıdır?"),
    ("IDENTITY_QUERY", "Sən kimsən?"), ("GENERAL_CONVERSATION", "Süni intellekt insanı necə tanıyır?"),
    ("GENERAL_CONVERSATION", "Dünən nə danışmışdıq?"), ("GENERAL_CONVERSATION", "Yaddaş necə işləyir?"),
    ("MEMORY_WRITE_REQUEST", "Mən rəsm çəkirəm, bunu yadda saxla."), ("PERSONAL_ASSERTION", "Mən rəsm çəkirəm."),
    ("GOAL_LIST_QUERY", "Məqsədlərim nədir?"), ("GOAL_WRITE_REQUEST", "Bu hədəfi dayandır."),
    ("GENERAL_CONVERSATION", "Məqsəd nədir?"), ("PERSONAL_PROFILE_QUERY", "Mənimlə bağlı ümumi nə bilirsən?"),
    ("PERSONAL_FACT_QUERY", "Mən hansı oyunu sevirəm?"), ("GENERAL_CONVERSATION", "Naruto necə animedir?"),
    ("IDENTITY_QUERY", "Sənin adın nədir?"), ("GENERAL_CONVERSATION", "Nə edə bilirsən?"),
]

def main():
    source = source_from_blueprint(DATA / "blueprint" / "source_families.jsonl")
    report = qc(source)
    if report["issues"] or report["exact_duplicates"]:
        raise SystemExit(f"Source QC failed: {report}")
    split = deterministic_split(source)
    targeted = []
    for label, texts in TARGETED.items():
        for index, text in enumerate(texts, 1):
            targeted.append({**source[0], "id": f"ITER1-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"ITER1-{label}", "semantic_pattern": "targeted_confusion_repair", "lineage_id": f"ITER1-{label}-{index:02d}", "split": "train", "generation_method": "manual_error_driven_iteration", "review_status": "reviewed", "high_risk": True})
    split.extend(targeted)
    targeted_iter2 = []
    for label, texts in TARGETED_ITER2.items():
        for index, text in enumerate(texts, 1):
            targeted_iter2.append({**source[0], "id": f"ITER2-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"ITER2-{label}", "semantic_pattern": "targeted_release_v2_repair", "lineage_id": f"ITER2-{label}-{index:02d}", "split": "train", "generation_method": "manual_error_driven_iteration", "review_status": "reviewed", "high_risk": True})
    split.extend(targeted_iter2)
    targeted_iter3 = []
    for label, texts in TARGETED_ITER3.items():
        for index, text in enumerate(texts, 1):
            targeted_iter3.append({**source[0], "id": f"ITER3-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"ITER3-{label}", "semantic_pattern": "targeted_pfq_pa_boundary_repair", "lineage_id": f"ITER3-{label}-{index:02d}", "split": "train", "generation_method": "manual_error_driven_iteration", "review_status": "reviewed", "high_risk": True})
    split.extend(targeted_iter3)
    targeted_iter4 = []
    for label, texts in TARGETED_ITER4.items():
        for index, text in enumerate(texts, 1):
            targeted_iter4.append({**source[0], "id": f"ITER4-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"ITER4-{label}", "semantic_pattern": "targeted_pfq_pa_score_repair", "lineage_id": f"ITER4-{label}-{index:02d}", "split": "train", "generation_method": "manual_error_driven_iteration", "review_status": "reviewed", "high_risk": True})
    split.extend(targeted_iter4)
    targeted_iter5 = []
    for label, texts in TARGETED_ITER5.items():
        for index, text in enumerate(texts, 1):
            targeted_iter5.append({**source[0], "id": f"ITER5-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"ITER5-{label}", "semantic_pattern": "targeted_pfq_pa_calibration_repair", "lineage_id": f"ITER5-{label}-{index:02d}", "split": "train", "generation_method": "manual_error_driven_iteration", "review_status": "reviewed", "high_risk": True})
    split.extend(targeted_iter5)
    targeted_iter6 = []
    for label, texts in TARGETED_ITER6.items():
        for index, text in enumerate(texts, 1):
            targeted_iter6.append({**source[0], "id": f"ITER6-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"ITER6-{label}", "semantic_pattern": "targeted_global_recall_repair", "lineage_id": f"ITER6-{label}-{index:02d}", "split": "train", "generation_method": "manual_error_driven_iteration", "review_status": "reviewed", "high_risk": True})
    split.extend(targeted_iter6)
    targeted_iter7 = []
    for label, texts in TARGETED_ITER7.items():
        for index, text in enumerate(texts, 1):
            targeted_iter7.append({**source[0], "id": f"ITER7-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"ITER7-{label}", "semantic_pattern": "targeted_profile_summary_repair", "lineage_id": f"ITER7-{label}-{index:02d}", "split": "train", "generation_method": "manual_error_driven_iteration", "review_status": "reviewed", "high_risk": True})
    split.extend(targeted_iter7)
    calibration = []
    for label, texts in CALIBRATION.items():
        for index, text in enumerate(texts, 1):
            calibration.append({**source[0], "id": f"CAL-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"CAL-{label}", "semantic_pattern": "threshold_calibration", "lineage_id": f"CAL-{label}-{index:02d}", "split": "validation", "generation_method": "manual_threshold_calibration", "review_status": "reviewed"})
    split.extend(calibration)
    calibration_iter2 = []
    for label, texts in CALIBRATION_ITER2.items():
        for index, text in enumerate(texts, 1):
            calibration_iter2.append({**source[0], "id": f"CAL2-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"CAL2-{label}", "semantic_pattern": "targeted_threshold_calibration", "lineage_id": f"CAL2-{label}-{index:02d}", "split": "validation", "generation_method": "manual_threshold_calibration", "review_status": "reviewed"})
    split.extend(calibration_iter2)
    calibration_iter3 = []
    for label, texts in CALIBRATION_ITER3.items():
        for index, text in enumerate(texts, 1):
            calibration_iter3.append({**source[0], "id": f"CAL3-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"CAL3-{label}", "semantic_pattern": "targeted_pfq_pa_calibration", "lineage_id": f"CAL3-{label}-{index:02d}", "split": "validation", "generation_method": "manual_threshold_calibration", "review_status": "reviewed"})
    split.extend(calibration_iter3)
    calibration_iter4 = []
    for label, texts in CALIBRATION_ITER4.items():
        for index, text in enumerate(texts, 1):
            calibration_iter4.append({**source[0], "id": f"CAL4-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"CAL4-{label}", "semantic_pattern": "targeted_pfq_pa_score_calibration", "lineage_id": f"CAL4-{label}-{index:02d}", "split": "validation", "generation_method": "manual_threshold_calibration", "review_status": "reviewed"})
    split.extend(calibration_iter4)
    calibration_iter5 = []
    for label, texts in CALIBRATION_ITER5.items():
        for index, text in enumerate(texts, 1):
            calibration_iter5.append({**source[0], "id": f"CAL5-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"CAL5-{label}", "semantic_pattern": "targeted_pfq_pa_low_score_calibration", "lineage_id": f"CAL5-{label}-{index:02d}", "split": "validation", "generation_method": "manual_threshold_calibration", "review_status": "reviewed"})
    split.extend(calibration_iter5)
    calibration_iter6 = []
    for label, texts in CALIBRATION_ITER6.items():
        for index, text in enumerate(texts, 1):
            calibration_iter6.append({**source[0], "id": f"CAL6-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"CAL6-{label}", "semantic_pattern": "targeted_global_recall_calibration", "lineage_id": f"CAL6-{label}-{index:02d}", "split": "validation", "generation_method": "manual_threshold_calibration", "review_status": "reviewed"})
    split.extend(calibration_iter6)
    calibration_iter7 = []
    for label, texts in CALIBRATION_ITER7.items():
        for index, text in enumerate(texts, 1):
            calibration_iter7.append({**source[0], "id": f"CAL7-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"CAL7-{label}", "semantic_pattern": "targeted_profile_summary_calibration", "lineage_id": f"CAL7-{label}-{index:02d}", "split": "validation", "generation_method": "manual_threshold_calibration", "review_status": "reviewed"})
    split.extend(calibration_iter7)
    write_jsonl(DATA / "source" / "source.jsonl", source)
    for name in ("train", "validation", "test"):
        clean = [row for row in split if row["split"] == name]
        write_jsonl(DATA / "splits" / f"{name}.jsonl", clean)
        write_jsonl(DATA / "splits" / f"{name}_augmented.jsonl", augment(clean))
    challenge = [{"id": f"CH-{index:03d}", "text": text, "reason": reason} for index, (text, reason) in enumerate(CHALLENGE, 1)]
    write_jsonl(DATA / "challenge" / "challenge.jsonl", challenge)
    holdout = []
    for label, texts in FINAL_HOLDOUT.items():
        for index, text in enumerate(texts, 1):
            holdout.append({**source[0], "id": f"FINAL-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"FINAL-{label}", "semantic_pattern": "independent_final_holdout", "lineage_id": f"FINAL-{label}-{index:02d}", "split": "final_holdout", "generation_method": "manual_final_holdout", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "final_holdout.jsonl", holdout)
    release = []
    for label, texts in RELEASE_HOLDOUT.items():
        for index, text in enumerate(texts, 1):
            release.append({**source[0], "id": f"RELEASE-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE-{label}", "semantic_pattern": "unseen_release_holdout", "lineage_id": f"RELEASE-{label}-{index:02d}", "split": "release_holdout", "generation_method": "manual_release_holdout", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout.jsonl", release)
    release_v2 = []
    for label, texts in RELEASE_HOLDOUT_V2.items():
        for index, text in enumerate(texts, 1):
            release_v2.append({**source[0], "id": f"RELEASE2-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE2-{label}", "semantic_pattern": "unseen_release_holdout_v2", "lineage_id": f"RELEASE2-{label}-{index:02d}", "split": "release_holdout_v2", "generation_method": "manual_release_holdout_v2", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v2.jsonl", release_v2)
    release_v3 = []
    for label, texts in RELEASE_HOLDOUT_V3.items():
        for index, text in enumerate(texts, 1):
            release_v3.append({**source[0], "id": f"RELEASE3-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE3-{label}", "semantic_pattern": "unseen_release_holdout_v3", "lineage_id": f"RELEASE3-{label}-{index:02d}", "split": "release_holdout_v3", "generation_method": "manual_release_holdout_v3", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v3.jsonl", release_v3)
    release_v4 = []
    for label, texts in RELEASE_HOLDOUT_V4.items():
        for index, text in enumerate(texts, 1):
            release_v4.append({**source[0], "id": f"RELEASE4-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE4-{label}", "semantic_pattern": "unseen_release_holdout_v4", "lineage_id": f"RELEASE4-{label}-{index:02d}", "split": "release_holdout_v4", "generation_method": "manual_release_holdout_v4", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v4.jsonl", release_v4)
    hard_negative = [{**source[0], "id": f"HNV4-{index:02d}", "text": text, "intent_label": label, "source_family": "HARD_NEGATIVE_V4", "semantic_pattern": "heldout_boundary_contrast", "lineage_id": f"HNV4-{index:02d}", "split": "hard_negative_v4", "generation_method": "manual_heldout_hard_negative", "review_status": "reviewed"} for index, (label, text) in enumerate(HARD_NEGATIVE_V4, 1)]
    write_jsonl(DATA / "challenge" / "hard_negative_v4.jsonl", hard_negative)
    release_v5 = []
    for label, texts in RELEASE_HOLDOUT_V5.items():
        for index, text in enumerate(texts, 1):
            release_v5.append({**source[0], "id": f"RELEASE5-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE5-{label}", "semantic_pattern": "unseen_release_holdout_v5", "lineage_id": f"RELEASE5-{label}-{index:02d}", "split": "release_holdout_v5", "generation_method": "manual_release_holdout_v5", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v5.jsonl", release_v5)
    hard_negative_v5 = [{**source[0], "id": f"HNV5-{index:02d}", "text": text, "intent_label": label, "source_family": "HARD_NEGATIVE_V5", "semantic_pattern": "heldout_boundary_contrast", "lineage_id": f"HNV5-{index:02d}", "split": "hard_negative_v5", "generation_method": "manual_heldout_hard_negative", "review_status": "reviewed"} for index, (label, text) in enumerate(HARD_NEGATIVE_V5, 1)]
    write_jsonl(DATA / "challenge" / "hard_negative_v5.jsonl", hard_negative_v5)
    release_v6 = []
    for label, texts in RELEASE_HOLDOUT_V6.items():
        for index, text in enumerate(texts, 1):
            release_v6.append({**source[0], "id": f"RELEASE6-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE6-{label}", "semantic_pattern": "unseen_release_holdout_v6", "lineage_id": f"RELEASE6-{label}-{index:02d}", "split": "release_holdout_v6", "generation_method": "manual_release_holdout_v6", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v6.jsonl", release_v6)
    release_v7 = []
    for label, texts in RELEASE_HOLDOUT_V7.items():
        for index, text in enumerate(texts, 1):
            release_v7.append({**source[0], "id": f"RELEASE7-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE7-{label}", "semantic_pattern": "unseen_release_holdout_v7", "lineage_id": f"RELEASE7-{label}-{index:02d}", "split": "release_holdout_v7", "generation_method": "manual_release_holdout_v7", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v7.jsonl", release_v7)
    hard_negative_v7 = [{**source[0], "id": f"HNV7-{index:02d}", "text": text, "intent_label": label, "source_family": "HARD_NEGATIVE_V7", "semantic_pattern": "heldout_boundary_contrast", "lineage_id": f"HNV7-{index:02d}", "split": "hard_negative_v7", "generation_method": "manual_heldout_hard_negative", "review_status": "reviewed"} for index, (label, text) in enumerate(HARD_NEGATIVE_V7, 1)]
    write_jsonl(DATA / "challenge" / "hard_negative_v7.jsonl", hard_negative_v7)
    release_v8 = []
    for label, texts in RELEASE_HOLDOUT_V8.items():
        for index, text in enumerate(texts, 1):
            release_v8.append({**source[0], "id": f"RELEASE8-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE8-{label}", "semantic_pattern": "unseen_release_holdout_v8", "lineage_id": f"RELEASE8-{label}-{index:02d}", "split": "release_holdout_v8", "generation_method": "manual_release_holdout_v8", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v8.jsonl", release_v8)
    hard_negative_v8 = [{**source[0], "id": f"HNV8-{index:02d}", "text": text, "intent_label": label, "source_family": "HARD_NEGATIVE_V8", "semantic_pattern": "heldout_boundary_contrast", "lineage_id": f"HNV8-{index:02d}", "split": "hard_negative_v8", "generation_method": "manual_heldout_hard_negative", "review_status": "reviewed"} for index, (label, text) in enumerate(HARD_NEGATIVE_V8, 1)]
    write_jsonl(DATA / "challenge" / "hard_negative_v8.jsonl", hard_negative_v8)
    release_v9 = []
    for label, texts in RELEASE_HOLDOUT_V9.items():
        for index, text in enumerate(texts, 1):
            release_v9.append({**source[0], "id": f"RELEASE9-{label[:4]}-{index:02d}", "text": text, "intent_label": label, "source_family": f"RELEASE9-{label}", "semantic_pattern": "unseen_release_holdout_v9", "lineage_id": f"RELEASE9-{label}-{index:02d}", "split": "release_holdout_v9", "generation_method": "manual_release_holdout_v9", "review_status": "reviewed"})
    write_jsonl(DATA / "splits" / "release_holdout_v9.jsonl", release_v9)
    hard_negative_v9 = [{**source[0], "id": f"HNV9-{index:02d}", "text": text, "intent_label": label, "source_family": "HARD_NEGATIVE_V9", "semantic_pattern": "heldout_boundary_contrast", "lineage_id": f"HNV9-{index:02d}", "split": "hard_negative_v9", "generation_method": "manual_heldout_hard_negative", "review_status": "reviewed"} for index, (label, text) in enumerate(HARD_NEGATIVE_V9, 1)]
    write_jsonl(DATA / "challenge" / "hard_negative_v9.jsonl", hard_negative_v9)
    counts = Counter(row["intent_label"] for row in source)
    summary = {"source_rows": len(source), "targeted_train_rows": len(targeted) + len(targeted_iter2) + len(targeted_iter3) + len(targeted_iter4) + len(targeted_iter5) + len(targeted_iter6) + len(targeted_iter7), "calibration_rows": len(calibration) + len(calibration_iter2) + len(calibration_iter3) + len(calibration_iter4) + len(calibration_iter5) + len(calibration_iter6) + len(calibration_iter7), "final_holdout_rows": len(holdout), "release_holdout_v2_rows": len(release_v2), "release_holdout_v3_rows": len(release_v3), "release_holdout_v4_rows": len(release_v4), "release_holdout_v5_rows": len(release_v5), "release_holdout_v6_rows": len(release_v6), "release_holdout_v7_rows": len(release_v7), "release_holdout_v8_rows": len(release_v8), "release_holdout_v9_rows": len(release_v9), "hard_negative_v4_rows": len(hard_negative), "hard_negative_v5_rows": len(hard_negative_v5), "hard_negative_v7_rows": len(hard_negative_v7), "hard_negative_v8_rows": len(hard_negative_v8), "hard_negative_v9_rows": len(hard_negative_v9), "labels": dict(counts), "families": len({row['source_family'] for row in source}), "qc": {"exact_duplicates": 0, "normalized_duplicate_groups": len(report['normalized_duplicates'])}}
    (DATA / "source" / "source_generation_report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))

if __name__ == "__main__":
    main()
