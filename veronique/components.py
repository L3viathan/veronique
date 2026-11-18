from veronique.constants import CLASSIFICATION_LEVELS
from veronique.html import H


def submit_button_with_classification(selected_level=0):
    return H.fieldset(
        H.select(
            *(
                H.option(level, value=str(i), selected=i==selected_level)
                for i, level in enumerate(CLASSIFICATION_LEVELS)
            ),
            name="level",
        ),
        H.button("\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}", type="submit"),
        role="group",
        cls="split-button",
    )


def header(title, subtitle=None, subsubtitle=None, hamburger_menu=(), avatar=None, extra=None, center=False):
    hamburger_menu = list(hamburger_menu)
    return H.header(
        H.h2(
            title,
            H(H.br(), H.small(subtitle, cls="subtitle")) if subtitle else None,
            H(H.br(), H.small(subsubtitle)) if subsubtitle else None,
            cls=["has-avatar" if avatar else None, "center" if center else None],
        ),
        avatar,
        hamburger(hamburger_menu) if hamburger_menu else None,
        extra,
    )


def hamburger(entries):
    return H.details(
        H.summary("\N{TRIGRAM FOR HEAVEN}"),
        H.ul(
            *(H.li(entry) for entry in entries),
            dir="rtl",
        ),
        cls="dropdown hamburger",
    )
