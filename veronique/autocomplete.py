from veronique.html import H


class Tags:
    def __init__(self, tagstring):
        self._data = {}
        for part in tagstring.split(","):
            key, _, value = part.partition("=")
            self._data[key] = value or None

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __str__(self):
        return ",".join(k if v is None else f"{k}={v}" for k, v in self._data.items())


def widget(tags, value=None):
    """
    Return an autocomplete widget. Tags specify properties of this
    autocomplete, including "what kind of thing are we autocompleting?", "Where
    does the result go?", "Are there multiple results?", etc.
    """
    show_cancel_button = "ir" in tags
    external_hits = "eh" in tags
    return H(
        H.div(
            H.fieldset(
                H.input(
                    name="value",
                    placeholder="Start typing...",
                    hx_get=f"/autocomplete/query?tags={tags}",
                    hx_target="next .ac-results",
                    hx_swap="innerMorph",
                    hx_trigger="input changed delay:200ms, search",
                    autocomplete="pleaseno",
                    autofocus=True,
                    value=value,
                ),
                H.input(
                    type="button",
                    value="x",
                    hx_swap="outerMorph",
                    hx_target=".ac-widget",
                    hx_get=f"/autocomplete/cancel?tags={tags}",
                ) if show_cancel_button else None,
                role="group",
            ),
            H.div("", cls="ac-results"),
            cls="ac-widget",
        ),
        H.div("", cls="ac-hits") if external_hits else None,
    )


def get_results(query, tags):
    import veronique.objects as O
    from veronique.data_types import TYPES
    if not query:
        return None
    connect = tags.get("connect")
    external_hits = "eh" in tags
    if data_type := tags.get("dt"):
        hits = TYPES[data_type].autocomplete(query)
    else:
        hits = [
            (c.id, c.html("label"))
            for c in O.Claim.search(
                q=query,
                page_size=5,
            )
        ]
    return H(
        *(
            H.a(
                hit_label,
                cls="clickable ac-result",
                hx_get=f"/autocomplete/accept/{hit_id}?tags={tags}",
                **({
                    "hx_target": "next .ac-hits",
                    "hx_swap": "beforeend",
                } if external_hits else {
                    "hx_target": "closest .ac-widget",
                    "hx_swap": "outerMorph",
                }),
            ) for hit_id, hit_label in hits
        ),
        H.a(
            H.em("Create"),
            f" {query} ",
            H.em("claim..."),
            cls="clickable",
            href=f"/claims/new-entity?connect={connect}&name={query}",
        ) if connect is not None else None
    )


def accept(hit, tags):
    import veronique.objects as O
    from veronique.data_types import TYPES
    input_ref = "ir" in tags
    input_field = tags.get("if", "value")
    if data_type := tags.get("dt"):
        return TYPES[data_type].input_html(value=hit)
    else:
        claim = O.Claim(int(hit))
    if input_ref:
        return H(claim.html("input-widget-ref"), "&nbsp;")
    return H(
        H.span(claim.html(), cls="ac-result"),
        H.input(type="hidden", name=input_field, value=str(hit)),
    )
