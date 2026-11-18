import random
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


def triple(claim, *, subject=False, object=False, sources=None, tooltip=None, valid=True, nested=False):
    if subject and object:
        css_classes = ["svo"]
    elif subject:
        css_classes = ["sv"]
    elif object:
        css_classes = ["vo"]
    if not valid:
        css_classes.append("invalid")
    if valid is None:
        css_classes.append("invalid-maybe")
    if nested:
        css_classes.append("nested")
    return H(
        H.span(
            claim.html("handle"),
            claim.subject.html("nested") if subject else None,
            " ",
            claim.verb.html("nested"),
            " ",
            claim.object.html("nested") if object else None,
            popover_menu(
                "\N{SPEECH BALLOON}",
                H(*(H.div(H(
                    source.html("handle"),
                    " ",
                    source.object.html(),
                )) for source in sources))
            ) if sources else None,
            cls=css_classes,
            data_tooltip=tooltip or None,
        ),
    )


def popover_menu(label, content):
    id = random.randint(1, 1000)
    src_id = f"--popover-{id}"
    return H(
        H.button(
            label,
            cls="popover-button",
            command="toggle-popover",
            commandfor=f"popover-{id}",
            interestfor=f"popover-{id}",
            style=f"anchor-name: {src_id};",
        ),
        H.div(
            content,
            id=f"popover-{id}",
            popover="hint",
            cls="inline-popover",
            style=f"position-anchor: {src_id};",
        )
    )


def pagination(url, page_no, *, more_results=True, allow_negative=False):
    if page_no == 1 and not more_results:
        return ""
    q = "&" if "?" in url else "?"
    if "page=" in url or "page=" in url:
        url_template = re.sub(r"page=\d+", "page={}", url)
    else:
        url_template = f"{url}{q}page={{}}"
    return H.footer(
        H.a(
            "&lt;",
            role="button",
            cls="prev",
            href=url_template.format(page_no - 1),
            disabled=page_no==1 and not allow_negative,
        ),
        H.a(
            "&gt;",
            role="button",
            cls="next",
            href=url_template.format(page_no + 1),
            disabled=not more_results,
        ),
    )
