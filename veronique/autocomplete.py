from veronique.html import H

AUTOCOMPLETES = {}


class Autocomplete:
    def __init_subclass__(cls):
        AUTOCOMPLETES[cls.__name__] = cls()


class input_ref_widget(Autocomplete):
    def widget(self, data=None):
        return H.div(
            H.fieldset(
                H.input(
                    name="ac-query",
                    placeholder="Start typing...",
                    hx_get=f"/autocomplete/input_ref_widget/query/{data}",
                    hx_target="next .ac-results",
                    hx_swap="innerMorph",
                    hx_trigger="input changed delay:200ms, search",
                    autocomplete="pleaseno",
                    autofocus=True,
                ),
                H.input(
                    type="button",
                    value="x",
                    hx_swap="outerMorph",
                    hx_target=".ac-widget",
                    hx_get="/types/text",
                ),
                role="group",
            ),
            H.div("", cls="ac-results"),
            cls="ac-widget",
        )

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return ""
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return H(
            *(
                H.a(
                    claim.html("label"),
                    cls="clickable ac-result",
                    hx_target="closest .ac-widget",
                    hx_swap="outerMorph",
                    hx_get=f"/autocomplete/input_ref_widget/accept/{claim.id}",
                )
                for claim in claims
            )
        ),

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        return H(claim.html("input-widget-ref"), "&nbsp;")


class link(Autocomplete):
    def widget(self, data=None):
        return H.div(
            H.input(
                name="ac-query",
                placeholder="Start typing...",
                hx_get=f"/autocomplete/link/query/{data}",
                hx_target="next .ac-results",
                hx_swap="innerMorph",
                hx_trigger="input changed delay:200ms, search",
            ),
            H.div("", cls="ac-results"),
            cls="ac-widget",
        )

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return ""
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return H(
            *(
                H.a(
                    claim.html("label"),
                    cls="clickable ac-result",
                    hx_target="closest .ac-widget",
                    hx_swap="outerMorph",
                    hx_get=f"/autocomplete/link/accept/{claim.id}",
                ) for claim in claims
            ),
            H.a(
                H.em("Create"),
                f" {query} ",
                H.em("claim..."),
                cls="clickable",
                href=f"/claims/new-entity?connect={connect}&name={query}",
            ) if connect is not None else None
        )

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        return H(
            H.span(claim.html(), cls="ac-result"),
            H.input(type="hidden", name="value", value=str(claim_id)),
        )


class multiselect(Autocomplete):
    def widget(self, data=None):
        return H(
            H.div(
                H.input(
                    name="ac-query",
                    placeholder="Start typing...",
                    hx_get=f"/autocomplete/multiselect/query/{data}",
                    hx_target="next .ac-results",
                    hx_swap="innerMorph",
                    hx_trigger="input changed delay:200ms, search",
                ),
                H.div("", cls="ac-results"),
                cls="ac-widget",
            ),
            H.div("", cls="ac-hits"),
        )

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return ""
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return H(
            *(
                H.a(
                    claim.html("label"),
                    cls="clickable ac-result",
                    hx_target="next .ac-hits",
                    hx_swap="beforeend",
                    hx_get=f"/autocomplete/multiselect/accept/{claim.id}",
                )
                for claim in claims
            )
        )

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        H(
            H.span(claim.html(), cls="ac-result"),
            H.input(type="hidden", name="value", value=str(claim_id)),
        )


class entity(Autocomplete):
    def widget(self, data=None):
        return H.div(
            H.input(
                name="ac-query",
                placeholder="Start typing...",
                hx_get=f"/autocomplete/entity/query/{data}",
                hx_target="next .ac-results",
                hx_swap="innerMorph",
                hx_trigger="input changed delay:200ms, search",
            ),
            H.div("", cls="ac-results"),
            cls="ac-widget",
        )

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return None
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return H(
            *(
                H.a(
                    claim.html("label"),
                    cls="clickable ac-result",
                    hx_target="closest .ac-widget",
                    hx_swap="outerMorph",
                    hx_get="/autocomplete/entity/accept/{claim.id}",
                )
                for claim in claims
            )
        )

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        return H(
            H.span(claim.html(), cls="ac-result"),
            H.input(type="hidden", name="entity_id", value=str(claim_id)),
        )
