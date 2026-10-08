"""Per-book language: a BCP 47 tag or a TeX babel name, plus chrome.

Body prose is whatever the author wrote. This module only names the
framework headings. A project with no language stays Spanish.
"""

import re
from dataclasses import dataclass

_EMPTY_PIECE = "Gap: this part of the draft has no stored material yet."
_SECTION_GAP = "Gap: this section has no paragraph tied to an opened excerpt."
_FIGURE_GAP = "Gap: this figure is unchecked. The drawing is omitted."
_KEYS = (
    "preface",
    "how",
    "audit",
    "study",
    "notation",
    "formulas",
    "solutions",
    "blueprint",
    "footer",
    "gap",
    "unwritten",
    "empty",
    "blocked",
    "purpose",
    "explanation",
    "worked",
    "self_check",
    "figure_gap",
    "caption",
    "subtitle",
    "status",
    "unreleased",
    "edition",
    "leftover",
    "note",
    "how_a",
    "how_b",
    "consejo",
    "definition",
    "section",
    "enunciado",
    "resolucion",
    "respuesta",
    "open_supplement",
    "not_guide",
    "contents",
    "two_witnesses",
    "replayed",
    "single_excerpt",
    "unchecked",
    "sources_heading",
    "excerpts_heading",
    "status_head",
    "pending_word",
    "conflicts",
    "guide_topic",
    "guide_course",
    "not_cited",
)

SPANISH_TWO_SECTIONS = (
    "This chapter needs at least two section blocks of explanation, not a single Explicación, "
    "plus the lead, one consejo, one worked problem, and one autoficha."
)
SPANISH_CHAPTER = (
    "Write a full chapter in Spanish, several paragraphs of explanation as body text, not a summary and not a sentence. "
    "The explanation needs at least two section blocks and 400 words. "
    "Use the same shape every chapter: a short lead, the explanation, at most one consejo, "
    "definitions only for new terms, one worked problem with enunciado, resolución, and respuesta, "
    "and one autoficha. "
    "Boxes are only those four. Cite stored excerpts. "
    "A formula must be quoted in an excerpt or replayed. "
    "A worked problem in a book that is not COMPUTER_SCIENCE is a replayed computation or a numeric result cited from two excerpts. "
    "Code behavior needs two sources or a test that passed 3 times. "
    "Do not ask the user how to format the page. The renderer owns the boxes."
)
INVALID_LANGUAGE = "language must be a BCP 47 tag or a TeX babel language name"

# pdfTeX drafts load babel. Polyglossia is only for a language babel cannot name.
_POLYGLOSSIA_ONLY: frozenset[str] = frozenset()

_ISO_TO_BABEL = {
    "af": "afrikaans",
    "ar": "arabic",
    "bg": "bulgarian",
    "br": "breton",
    "ca": "catalan",
    "cop": "coptic",
    "cs": "czech",
    "cy": "welsh",
    "da": "danish",
    "de": "ngerman",
    "el": "greek",
    "en": "english",
    "eo": "esperanto",
    "es": "spanish",
    "et": "estonian",
    "eu": "basque",
    "fa": "farsi",
    "fi": "finnish",
    "fr": "french",
    "fur": "friulan",
    "ga": "irish",
    "gd": "scottish",
    "gl": "galician",
    "he": "hebrew",
    "hr": "croatian",
    "hsb": "uppersorbian",
    "hu": "hungarian",
    "hy": "armenian",
    "ia": "interlingua",
    "id": "indonesian",
    "is": "icelandic",
    "it": "italian",
    "ka": "georgian",
    "kmr": "kurmanji",
    "la": "latin",
    "lt": "lithuanian",
    "lv": "latvian",
    "mn": "mongolian",
    "ms": "malay",
    "nb": "bokmal",
    "nl": "dutch",
    "nn": "nynorsk",
    "no": "norsk",
    "oc": "occitan",
    "pl": "polish",
    "pms": "piedmontese",
    "pt": "portuguese",
    "rm": "romansh",
    "ro": "romanian",
    "ru": "russian",
    "sa": "sanskrit",
    "se": "samin",
    "sk": "slovak",
    "sl": "slovene",
    "sq": "albanian",
    "sr": "serbian",
    "sv": "swedish",
    "th": "thai",
    "tk": "turkmen",
    "tr": "turkish",
    "uk": "ukrainian",
    "vi": "vietnamese",
    "zh": "pinyin",
}
_REGION_TO_BABEL = {
    "de-at": "naustrian",
    "de-de": "ngerman",
    "en-au": "australian",
    "en-ca": "canadian",
    "en-gb": "british",
    "en-nz": "newzealand",
    "en-us": "american",
    "fr-ca": "canadien",
    "pt-br": "brazilian",
}
_EXTRA_BABEL = frozenset(
    {
        "acadian",
        "ancientgreek",
        "austrian",
        "bahasa",
        "bahasai",
        "bahasam",
        "brazil",
        "brazilian",
        "british",
        "canadian",
        "canadien",
        "classiclatin",
        "english",
        "francais",
        "french",
        "german",
        "germanb",
        "magyar",
        "monogreek",
        "naustrian",
        "ngerman",
        "ngermanb",
        "norsk",
        "norwegian",
        "patois",
        "polutonikogreek",
        "portuges",
        "serbianc",
        "slovenian",
        "spanish",
        "ukenglish",
        "usenglish",
    }
)
_BABEL_NAMES = frozenset(_ISO_TO_BABEL.values()) | frozenset(_REGION_TO_BABEL.values()) | _EXTRA_BABEL
_BABEL_TO_CATALOG = {
    "acadian": "fr",
    "american": "en",
    "australian": "en",
    "austrian": "de",
    "brazil": "pt",
    "brazilian": "pt",
    "british": "en",
    "canadian": "en",
    "canadien": "fr",
    "catalan": "ca",
    "english": "en",
    "francais": "fr",
    "french": "fr",
    "galician": "gl",
    "german": "de",
    "germanb": "de",
    "italian": "it",
    "naustrian": "de",
    "ngerman": "de",
    "ngermanb": "de",
    "patois": "fr",
    "portuges": "pt",
    "portuguese": "pt",
    "spanish": "es",
    "ukenglish": "en",
    "usenglish": "en",
}
_BABEL_ENGLISH = {
    "afrikaans": "Afrikaans",
    "albanian": "Albanian",
    "american": "English",
    "arabic": "Arabic",
    "australian": "English",
    "basque": "Basque",
    "bokmal": "Norwegian",
    "brazilian": "Portuguese",
    "breton": "Breton",
    "british": "English",
    "bulgarian": "Bulgarian",
    "canadian": "English",
    "canadien": "French",
    "catalan": "Catalan",
    "croatian": "Croatian",
    "czech": "Czech",
    "danish": "Danish",
    "dutch": "Dutch",
    "english": "English",
    "esperanto": "Esperanto",
    "estonian": "Estonian",
    "farsi": "Persian",
    "finnish": "Finnish",
    "francais": "French",
    "french": "French",
    "galician": "Galician",
    "german": "German",
    "greek": "Greek",
    "hebrew": "Hebrew",
    "hungarian": "Hungarian",
    "icelandic": "Icelandic",
    "indonesian": "Indonesian",
    "irish": "Irish",
    "italian": "Italian",
    "latin": "Latin",
    "lithuanian": "Lithuanian",
    "latvian": "Latvian",
    "malay": "Malay",
    "naustrian": "German",
    "newzealand": "English",
    "ngerman": "German",
    "norsk": "Norwegian",
    "nynorsk": "Norwegian",
    "polish": "Polish",
    "portuguese": "Portuguese",
    "romanian": "Romanian",
    "russian": "Russian",
    "slovak": "Slovak",
    "slovene": "Slovenian",
    "spanish": "Spanish",
    "swedish": "Swedish",
    "thai": "Thai",
    "turkish": "Turkish",
    "ukrainian": "Ukrainian",
    "vietnamese": "Vietnamese",
    "welsh": "Welsh",
}
_TAG = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8}){1,3}$")


@dataclass(frozen=True)
class BookLanguage:
    """Stored tag, chrome catalog code, and the TeX language to load."""

    tag: str
    catalog: str
    babel: str
    loader: str
    legacy: bool = False


def _entry(**kwargs: str) -> dict[str, str]:
    missing = [key for key in _KEYS if key not in kwargs]
    extra = [key for key in kwargs if key not in _KEYS]
    if missing or extra:
        raise RuntimeError(f"language catalog keys missing={missing} extra={extra}")
    return dict(kwargs)


_SPANISH = _entry(
    preface="Prefacio",
    how="Cómo usar este libro",
    audit="Auditoría de fuentes",
    study="Plan de estudio",
    notation="Notación",
    formulas="Hoja de fórmulas",
    solutions="Soluciones",
    blueprint="Esquema",
    footer="Borrador",
    gap="Esta sección está vacía.",
    unwritten="todavía no está escrito",
    empty="Esta parte del borrador aún no tiene material.",
    blocked="Bloqueado: no hay un segundo extracto abierto independiente ni una comprobación rehecha.",
    purpose="Consejo",
    explanation="Definición",
    worked="Problema resuelto",
    self_check="Autoficha",
    figure_gap="Esta figura no está comprobada. El dibujo se omite.",
    caption="La cifra del pie sigue sin comprobar.",
    subtitle="Apuntes de trabajo",
    status="Borrador",
    unreleased="No publicado",
    edition="Edición",
    leftover="Borrador antiguo.",
    note=(
        "Este libro presenta el tema con el lenguaje del curso. "
        "Cada capítulo abre con una entrada breve, sigue con la explicación "
        "y cierra con un problema resuelto y una autoficha."
    ),
    how_a=(
        "Lee el capítulo seguido. El consejo, la definición, el problema resuelto "
        "y la autoficha van en recuadros. La explicación es el cuerpo del texto."
    ),
    how_b=(
        "Un capítulo lleva una entrada en cursiva, la explicación en el cuerpo, como mucho un consejo, "
        "definiciones solo al introducir un término, un problema resuelto y una autoficha."
    ),
    consejo="Consejo",
    definition="Definición",
    section="Explicación",
    enunciado="Enunciado",
    resolucion="Resolución",
    respuesta="Respuesta",
    open_supplement="Suplemento abierto:",
    not_guide="No es la bibliografía de la guía.",
    contents="Índice",
    two_witnesses="dos testimonios",
    replayed="comprobación rehecha",
    single_excerpt="un extracto",
    unchecked="sin comprobar",
    sources_heading="Fuentes",
    excerpts_heading="Extractos",
    status_head="Estado de las fuentes: PENDING.",
    pending_word="pendientes",
    conflicts="Los conflictos almacenados quedan fuera ({n}).",
    guide_topic="Un libro de tema no usa una guía universitaria, así que no citada no es una regla de apoyo.",
    guide_course="Las fuentes que la guía almacenada no cita quedan fuera.",
    not_cited="Recuento de no citadas: {n}.",
)
_ENGLISH = _entry(
    preface="Preface",
    how="How to use this book",
    audit="Source audit",
    study="Study plan",
    notation="Notation",
    formulas="Formula sheet",
    solutions="Solutions",
    blueprint="Blueprint",
    footer="DRAFT",
    gap=_SECTION_GAP,
    unwritten="not written yet",
    empty=_EMPTY_PIECE,
    blocked="Blocked: no second independent open excerpt and no replayed check.",
    purpose="Tip",
    explanation="Definition",
    worked="Worked problem",
    self_check="Self-check",
    figure_gap=_FIGURE_GAP,
    caption="The numeric claim in the caption is unchecked.",
    subtitle="Working notes",
    status="Draft",
    unreleased="Not released",
    edition="Edition",
    leftover="Leftover draft.",
    note="This file is a DRAFT. It is not RELEASED.",
    how_a="A section may hold several paragraphs. Each substantive paragraph cites a stored excerpt.",
    how_b=(
        "A chapter has an italic lead, the explanation as body text, at most one tip, "
        "definitions only when a term is introduced, one worked problem, and one self-check."
    ),
    consejo="Tip",
    definition="Definition",
    section="Explanation",
    enunciado="Statement",
    resolucion="Solution",
    respuesta="Answer",
    open_supplement="Open supplement:",
    not_guide="Not the guide bibliography.",
    contents="Contents",
    two_witnesses="two_witnesses",
    replayed="replayed check",
    single_excerpt="single excerpt",
    unchecked="unchecked",
    sources_heading="Sources",
    excerpts_heading="Excerpts",
    status_head="Source status: PENDING.",
    pending_word="pending",
    conflicts="Stored conflicts stay excluded ({n}).",
    guide_topic="A topic book does not use a university guide, so not cited is not a support rule.",
    guide_course="Sources not cited by the stored course guide stay excluded.",
    not_cited="Not cited count: {n}.",
)
_FRENCH = _entry(
    preface="Préface",
    how="Comment utiliser ce livre",
    audit="Audit des sources",
    study="Plan d'étude",
    notation="Notation",
    formulas="Formulaire",
    solutions="Solutions",
    blueprint="Plan",
    footer="Brouillon",
    gap="Cette section est vide.",
    unwritten="pas encore écrit",
    empty="Cette partie du brouillon n'a pas encore de contenu.",
    blocked="Bloqué : pas de second extrait ouvert indépendant ni de vérification rejouée.",
    purpose="Conseil",
    explanation="Définition",
    worked="Problème résolu",
    self_check="Autocontrôle",
    figure_gap="Cette figure n'est pas vérifiée. Le dessin est omis.",
    caption="Le nombre dans la légende n'est pas vérifié.",
    subtitle="Notes de travail",
    status="Brouillon",
    unreleased="Non publié",
    edition="Édition",
    leftover="Ancien brouillon.",
    note=(
        "Ce livre présente le sujet dans la langue du livre. "
        "Chaque chapitre s'ouvre sur une entrée brève, poursuit par l'explication "
        "et se termine par un problème résolu et un autocontrôle."
    ),
    how_a=(
        "Lis le chapitre d'une traite. Le conseil, la définition, le problème résolu "
        "et l'autocontrôle sont dans des encadrés. L'explication est le corps du texte."
    ),
    how_b=(
        "Un chapitre a une entrée en italique, l'explication dans le corps, au plus un conseil, "
        "des définitions seulement pour un terme nouveau, un problème résolu et un autocontrôle."
    ),
    consejo="Conseil",
    definition="Définition",
    section="Explication",
    enunciado="Énoncé",
    resolucion="Résolution",
    respuesta="Réponse",
    open_supplement="Supplément ouvert :",
    not_guide="Ce n'est pas la bibliographie du guide.",
    contents="Table des matières",
    two_witnesses="deux témoins",
    replayed="vérification rejouée",
    single_excerpt="un extrait",
    unchecked="non vérifié",
    sources_heading="Sources",
    excerpts_heading="Extraits",
    status_head="État des sources : PENDING.",
    pending_word="en attente",
    conflicts="Les conflits enregistrés restent exclus ({n}).",
    guide_topic="Un livre de sujet n'utilise pas de guide universitaire, donc non cité n'est pas une règle d'appui.",
    guide_course="Les sources que le guide enregistré ne cite pas restent exclues.",
    not_cited="Nombre de non citées : {n}.",
)
_GERMAN = _entry(
    preface="Vorwort",
    how="Zum Gebrauch dieses Buches",
    audit="Quellenprüfung",
    study="Lernplan",
    notation="Notation",
    formulas="Formelblatt",
    solutions="Lösungen",
    blueprint="Gliederung",
    footer="Entwurf",
    gap="Dieser Abschnitt ist leer.",
    unwritten="noch nicht geschrieben",
    empty="Dieser Teil des Entwurfs hat noch kein Material.",
    blocked="Blockiert: kein zweites unabhängiges offenes Exzerpt und keine wiederholte Prüfung.",
    purpose="Hinweis",
    explanation="Definition",
    worked="Gelöste Aufgabe",
    self_check="Selbstkontrolle",
    figure_gap="Diese Abbildung ist ungeprüft. Die Zeichnung entfällt.",
    caption="Die Zahl in der Bildunterschrift ist ungeprüft.",
    subtitle="Arbeitsnotizen",
    status="Entwurf",
    unreleased="Nicht veröffentlicht",
    edition="Ausgabe",
    leftover="Alter Entwurf.",
    note=(
        "Dieses Buch stellt das Thema in der Sprache des Buches dar. "
        "Jedes Kapitel beginnt mit einem kurzen Einstieg, führt die Erklärung aus "
        "und schließt mit einer gelösten Aufgabe und einer Selbstkontrolle."
    ),
    how_a=(
        "Lies das Kapitel am Stück. Hinweis, Definition, gelöste Aufgabe "
        "und Selbstkontrolle stehen in Kästen. Die Erklärung ist der Fließtext."
    ),
    how_b=(
        "Ein Kapitel hat einen kursiven Einstieg, die Erklärung im Fließtext, höchstens einen Hinweis, "
        "Definitionen nur für einen neuen Begriff, eine gelöste Aufgabe und eine Selbstkontrolle."
    ),
    consejo="Hinweis",
    definition="Definition",
    section="Erklärung",
    enunciado="Aufgabenstellung",
    resolucion="Lösung",
    respuesta="Antwort",
    open_supplement="Offene Ergänzung:",
    not_guide="Nicht die Literatur der Kursbeschreibung.",
    contents="Inhaltsverzeichnis",
    two_witnesses="zwei Zeugen",
    replayed="wiederholte Prüfung",
    single_excerpt="ein Auszug",
    unchecked="ungeprüft",
    sources_heading="Quellen",
    excerpts_heading="Auszüge",
    status_head="Quellenstand: PENDING.",
    pending_word="ausstehend",
    conflicts="Gespeicherte Konflikte bleiben ausgeschlossen ({n}).",
    guide_topic="Ein Themenbuch nutzt keinen Universitätsleitfaden, daher ist nicht zitiert keine Stützungsregel.",
    guide_course="Quellen, die der gespeicherte Leitfaden nicht zitiert, bleiben ausgeschlossen.",
    not_cited="Anzahl der nicht zitierten: {n}.",
)
_PORTUGUESE = _entry(
    preface="Prefácio",
    how="Como usar este livro",
    audit="Auditoria das fontes",
    study="Plano de estudo",
    notation="Notação",
    formulas="Folha de fórmulas",
    solutions="Soluções",
    blueprint="Esquema",
    footer="Rascunho",
    gap="Esta secção está vazia.",
    unwritten="ainda não está escrito",
    empty="Esta parte do rascunho ainda não tem material.",
    blocked="Bloqueado: não há um segundo excerto aberto independente nem uma verificação repetida.",
    purpose="Conselho",
    explanation="Definição",
    worked="Problema resolvido",
    self_check="Autoverificação",
    figure_gap="Esta figura não está verificada. O desenho é omitido.",
    caption="O número da legenda continua por verificar.",
    subtitle="Notas de trabalho",
    status="Rascunho",
    unreleased="Não publicado",
    edition="Edição",
    leftover="Rascunho antigo.",
    note=(
        "Este livro apresenta o tema na língua do livro. "
        "Cada capítulo abre com uma entrada breve, segue com a explicação "
        "e fecha com um problema resolvido e uma autoverificação."
    ),
    how_a=(
        "Lê o capítulo seguido. O conselho, a definição, o problema resolvido "
        "e a autoverificação vão em caixas. A explicação é o corpo do texto."
    ),
    how_b=(
        "Um capítulo tem uma entrada em itálico, a explicação no corpo, no máximo um conselho, "
        "definições só ao introduzir um termo, um problema resolvido e uma autoverificação."
    ),
    consejo="Conselho",
    definition="Definição",
    section="Explicação",
    enunciado="Enunciado",
    resolucion="Resolução",
    respuesta="Resposta",
    open_supplement="Suplemento aberto:",
    not_guide="Não é a bibliografia do guia.",
    contents="Índice",
    two_witnesses="dois testemunhos",
    replayed="verificação repetida",
    single_excerpt="um excerto",
    unchecked="por verificar",
    sources_heading="Fontes",
    excerpts_heading="Excertos",
    status_head="Estado das fontes: PENDING.",
    pending_word="pendentes",
    conflicts="Os conflitos armazenados ficam de fora ({n}).",
    guide_topic="Um livro de tema não usa um guia universitário, por isso não citada não é uma regra de apoio.",
    guide_course="As fontes que o guia armazenado não cita ficam de fora.",
    not_cited="Contagem de não citadas: {n}.",
)
_ITALIAN = _entry(
    preface="Prefazione",
    how="Come usare questo libro",
    audit="Revisione delle fonti",
    study="Piano di studio",
    notation="Notazione",
    formulas="Foglio delle formule",
    solutions="Soluzioni",
    blueprint="Schema",
    footer="Bozza",
    gap="Questa sezione è vuota.",
    unwritten="non è ancora scritto",
    empty="Questa parte della bozza non ha ancora materiale.",
    blocked="Bloccato: manca un secondo estratto aperto indipendente e un controllo ripetuto.",
    purpose="Consiglio",
    explanation="Definizione",
    worked="Problema svolto",
    self_check="Autoverifica",
    figure_gap="Questa figura non è verificata. Il disegno è omesso.",
    caption="Il numero nella didascalia non è verificato.",
    subtitle="Note di lavoro",
    status="Bozza",
    unreleased="Non pubblicato",
    edition="Edizione",
    leftover="Bozza precedente.",
    note=(
        "Questo libro presenta il tema nella lingua del libro. "
        "Ogni capitolo si apre con un ingresso breve, prosegue con la spiegazione "
        "e si chiude con un problema svolto e un'autoverifica."
    ),
    how_a=(
        "Leggi il capitolo di seguito. Il consiglio, la definizione, il problema svolto "
        "e l'autoverifica stanno nei riquadri. La spiegazione è il corpo del testo."
    ),
    how_b=(
        "Un capitolo ha un ingresso in corsivo, la spiegazione nel corpo, al massimo un consiglio, "
        "definizioni solo per un termine nuovo, un problema svolto e un'autoverifica."
    ),
    consejo="Consiglio",
    definition="Definizione",
    section="Spiegazione",
    enunciado="Enunciato",
    resolucion="Risoluzione",
    respuesta="Risposta",
    open_supplement="Supplemento aperto:",
    not_guide="Non è la bibliografia della guida.",
    contents="Indice",
    two_witnesses="due testimoni",
    replayed="controllo ripetuto",
    single_excerpt="un estratto",
    unchecked="non verificato",
    sources_heading="Fonti",
    excerpts_heading="Estratti",
    status_head="Stato delle fonti: PENDING.",
    pending_word="in attesa",
    conflicts="I conflitti memorizzati restano esclusi ({n}).",
    guide_topic="Un libro di argomento non usa una guida universitaria, quindi non citato non è una regola di supporto.",
    guide_course="Le fonti che la guida memorizzata non cita restano escluse.",
    not_cited="Conteggio delle non citate: {n}.",
)
_CATALAN = _entry(
    preface="Prefaci",
    how="Com usar aquest llibre",
    audit="Auditoria de fonts",
    study="Pla d'estudi",
    notation="Notació",
    formulas="Full de fórmules",
    solutions="Solucions",
    blueprint="Esquema",
    footer="Esborrany",
    gap="Aquesta secció és buida.",
    unwritten="encara no està escrit",
    empty="Aquesta part de l'esborrany encara no té material.",
    blocked="Bloquejat: no hi ha un segon extracte obert independent ni una comprovació repetida.",
    purpose="Consell",
    explanation="Definició",
    worked="Problema resolt",
    self_check="Autocomprovació",
    figure_gap="Aquesta figura no està comprovada. El dibuix s'omet.",
    caption="La xifra del peu segueix sense comprovar.",
    subtitle="Notes de treball",
    status="Esborrany",
    unreleased="No publicat",
    edition="Edició",
    leftover="Esborrany antic.",
    note=(
        "Aquest llibre presenta el tema en la llengua del llibre. "
        "Cada capítol s'obre amb una entrada breu, segueix amb l'explicació "
        "i es tanca amb un problema resolt i una autocomprovació."
    ),
    how_a=(
        "Llegeix el capítol seguit. El consell, la definició, el problema resolt "
        "i l'autocomprovació van en requadres. L'explicació és el cos del text."
    ),
    how_b=(
        "Un capítol té una entrada en cursiva, l'explicació al cos, com a màxim un consell, "
        "definicions només en introduir un terme, un problema resolt i una autocomprovació."
    ),
    consejo="Consell",
    definition="Definició",
    section="Explicació",
    enunciado="Enunciat",
    resolucion="Resolució",
    respuesta="Resposta",
    open_supplement="Suplement obert:",
    not_guide="No és la bibliografia de la guia.",
    contents="Índex",
    two_witnesses="dos testimonis",
    replayed="comprovació repetida",
    single_excerpt="un extracte",
    unchecked="sense comprovar",
    sources_heading="Fonts",
    excerpts_heading="Extractes",
    status_head="Estat de les fonts: PENDING.",
    pending_word="pendents",
    conflicts="Els conflictes emmagatzemats queden fora ({n}).",
    guide_topic="Un llibre de tema no fa servir una guia universitària, així que no citada no és una regla de suport.",
    guide_course="Les fonts que la guia emmagatzemada no cita queden fora.",
    not_cited="Recompte de no citades: {n}.",
)
_GALICIAN = _entry(
    preface="Prefacio",
    how="Como usar este libro",
    audit="Auditoría de fontes",
    study="Plan de estudo",
    notation="Notación",
    formulas="Folla de fórmulas",
    solutions="Solucións",
    blueprint="Esquema",
    footer="Borrador",
    gap="Esta sección está baleira.",
    unwritten="aínda non está escrito",
    empty="Esta parte do borrador aínda non ten material.",
    blocked="Bloqueado: non hai un segundo extracto aberto independente nin unha comprobación refeita.",
    purpose="Consello",
    explanation="Definición",
    worked="Problema resolto",
    self_check="Autocomprobación",
    figure_gap="Esta figura non está comprobada. O debuxo omítese.",
    caption="A cifra do pé segue sen comprobar.",
    subtitle="Notas de traballo",
    status="Borrador",
    unreleased="Non publicado",
    edition="Edición",
    leftover="Borrador antigo.",
    note=(
        "Este libro presenta o tema na lingua do libro. "
        "Cada capítulo abre cunha entrada breve, segue coa explicación "
        "e pecha cun problema resolto e unha autocomprobación."
    ),
    how_a=(
        "Le o capítulo seguido. O consello, a definición, o problema resolto "
        "e a autocomprobación van en recadros. A explicación é o corpo do texto."
    ),
    how_b=(
        "Un capítulo leva unha entrada en cursiva, a explicación no corpo, como moito un consello, "
        "definicións só ao introducir un termo, un problema resolto e unha autocomprobación."
    ),
    consejo="Consello",
    definition="Definición",
    section="Explicación",
    enunciado="Enunciado",
    resolucion="Resolución",
    respuesta="Resposta",
    open_supplement="Suplemento aberto:",
    not_guide="Non é a bibliografía da guía.",
    contents="Índice",
    two_witnesses="dous testemuños",
    replayed="comprobación refeita",
    single_excerpt="un extracto",
    unchecked="sen comprobar",
    sources_heading="Fontes",
    excerpts_heading="Extractos",
    status_head="Estado das fontes: PENDING.",
    pending_word="pendentes",
    conflicts="Os conflitos almacenados quedan fóra ({n}).",
    guide_topic="Un libro de tema non usa unha guía universitaria, así que non citada non é unha regra de apoio.",
    guide_course="As fontes que a guía almacenada non cita quedan fóra.",
    not_cited="Reconto de non citadas: {n}.",
)
_CATALOG = {
    "es": _SPANISH,
    "en": _ENGLISH,
    "fr": _FRENCH,
    "de": _GERMAN,
    "pt": _PORTUGUESE,
    "it": _ITALIAN,
    "ca": _CATALAN,
    "gl": _GALICIAN,
}


def canonical_language(value: str) -> str | None:
    """Normalized tag, or None when the code is empty or not a real language."""

    described = describe(value)
    if described is None:
        return None
    return described.tag


def describe(value: str, *, legacy: bool = False) -> BookLanguage | None:
    """Parse a stored language. None means the code is not a real language."""

    cleaned = value.strip().lower().replace("_", "-")
    if not cleaned or len(cleaned) > 32 or not re.fullmatch(r"[a-z0-9-]+", cleaned):
        return None
    babel = _babel_name(cleaned)
    if babel is None or not re.fullmatch(r"[a-z]+", babel):
        return None
    loader = "polyglossia" if babel in _POLYGLOSSIA_ONLY else "babel"
    return BookLanguage(
        tag=cleaned,
        catalog=_catalog_code(cleaned, babel),
        babel=babel,
        loader=loader,
        legacy=legacy,
    )


def messages(language: BookLanguage) -> dict[str, str]:
    """Chrome for this book. A language with no catalog entry uses English."""

    return _CATALOG.get(language.catalog, _ENGLISH)


def writing_name(language: BookLanguage) -> str:
    """English name of the language the author should write in."""

    named = _BABEL_ENGLISH.get(language.babel)
    if named:
        return named
    return language.babel[:1].upper() + language.babel[1:]


def is_spanish_book(language: BookLanguage) -> bool:
    return language.babel == "spanish"


def is_spanish_tag(value: str | None) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    described = describe(value)
    return described is not None and described.babel == "spanish"


def chapter_contract(language: BookLanguage) -> str:
    """Tell the writer which language and which framework titles to use."""

    if is_spanish_book(language):
        return SPANISH_CHAPTER
    copy = messages(language)
    return (
        f"Write a full chapter in {writing_name(language)}, several paragraphs of explanation as body text, "
        "not a summary and not a sentence. "
        "The explanation needs at least two section blocks and 400 words. "
        f"Use the same shape every chapter: a short lead, the explanation, at most one {copy['consejo']}, "
        "definitions only for new terms, "
        f"one worked problem with {copy['enunciado']}, {copy['resolucion']}, and {copy['respuesta']}, "
        f"and one {copy['self_check']}. "
        "Boxes are only those four. Cite stored excerpts. "
        "A formula must be quoted in an excerpt or replayed. "
        "A worked problem in a book that is not COMPUTER_SCIENCE is a replayed computation or a numeric result cited from two excerpts. "
        "Code behavior needs two sources or a test that passed 3 times. "
        "Do not ask the user how to format the page. The renderer owns the boxes."
    )


def two_sections_line(language: BookLanguage) -> str:
    if is_spanish_book(language):
        return SPANISH_TWO_SECTIONS
    copy = messages(language)
    return (
        "This chapter needs at least two section blocks of explanation, not a single "
        f"{copy['section']}, plus the lead, one {copy['consejo']}, one worked problem, and one {copy['self_check']}."
    )


def resolution_labels(language: BookLanguage) -> str:
    if is_spanish_book(language):
        return "enunciado, resolución, and respuesta"
    copy = messages(language)
    return f"{copy['enunciado']}, {copy['resolucion']}, and {copy['respuesta']}"


def tip_word(language: BookLanguage) -> str:
    if is_spanish_book(language):
        return "consejo"
    return messages(language)["consejo"]


def self_check_word(language: BookLanguage) -> str:
    if is_spanish_book(language):
        return "autoficha"
    return messages(language)["self_check"]


def generic_section_titles() -> frozenset[str]:
    """Headings that are the framework word for explanation, not the author's title."""

    titles = {"explicación", "explicacion", "explanation"}
    for copy in _CATALOG.values():
        titles.add(copy["section"].casefold())
    return frozenset(titles)


def status_line(language: BookLanguage, *, topic: bool, pending: int, conflicting: int, not_cited: int) -> str:
    copy = messages(language)
    guide = copy["guide_topic"] if topic else copy["guide_course"]
    return (
        f"{copy['status_head']} "
        f"{pending} {copy['pending_word']}. "
        f"{copy['conflicts'].format(n=conflicting)} "
        f"{guide} "
        f"{copy['not_cited'].format(n=not_cited)}"
    )


def _babel_name(tag: str) -> str | None:
    if "-" not in tag and tag in _BABEL_NAMES:
        return tag
    regional = _REGION_TO_BABEL.get(tag)
    if regional is not None:
        return regional
    if "-" in tag:
        if _TAG.fullmatch(tag) is None:
            return None
        return _ISO_TO_BABEL.get(tag.split("-", 1)[0])
    if not re.fullmatch(r"[a-z]{2,3}", tag):
        return None
    return _ISO_TO_BABEL.get(tag)


def _catalog_code(tag: str, babel: str) -> str:
    mapped = _BABEL_TO_CATALOG.get(babel)
    if mapped is not None:
        return mapped
    primary = tag.split("-", 1)[0]
    if primary in _CATALOG:
        return primary
    return "en"
