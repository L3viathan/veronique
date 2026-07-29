AUTOCOMPLETES = {}


class Autocomplete:
    def __init_subclass__(cls):
        AUTOCOMPLETES[cls.__name__] = cls()


class input_ref_widget(Autocomplete):
    def widget(self, data=None):
        return f"""
            <div class="ac-widget">
                <fieldset role="group">
                <input
                    name="ac-query"
                    placeholder="Start typing..."
                    hx-get="/autocomplete/input_ref_widget/query/{data}"
                    hx-target="next .ac-results"
                    hx-swap="innerHTML"
                    hx-trigger="input changed delay:200ms, search"
                    autocomplete="pleaseno"
                    autofocus
                >
                <input type="button" value="x" hx-swap="outerHTML" hx-target=".ac-widget" hx-get="/verbs/data-types/text">
                </fieldset>
                <div class="ac-results">
                </div>
            </div>
        """

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return ""
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return f"""
        {"".join(f'''<a
            class="clickable ac-result"
            hx-target="closest .ac-widget"
            hx-swap="outerHTML"
            hx-get="/autocomplete/input_ref_widget/accept/{claim.id}"
        >{claim:label}</a>
        ''' for claim in claims)}
        """

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        return f"{claim:input-widget-ref}&nbsp;"

class link(Autocomplete):
    def widget(self, data=None):
        return f"""
            <div class="ac-widget">
                <input
                    name="ac-query"
                    placeholder="Start typing..."
                    hx-get="/autocomplete/link/query/{data}"
                    hx-target="next .ac-results"
                    hx-swap="innerHTML"
                    hx-trigger="input changed delay:200ms, search"
                >
                <div class="ac-results">
                </div>
            </div>
        """

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return ""
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return f"""
        {"".join(f'''<a
            class="clickable ac-result"
            hx-target="closest .ac-widget"
            hx-swap="outerHTML"
            hx-get="/autocomplete/link/accept/{claim.id}"
        >{claim:label}</a>
        ''' for claim in claims)}
        {f'''<a class="clickable" href="/claims/new-entity?connect={connect}&name={query}">
            <em>Create</em> {query} <em> claim...</em>
        </a>''' if connect is not None else ''}
        """

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        return f"""
        <span class="ac-result">{claim}</span>
        <input type="hidden" name="value" value="{claim_id}">
        """


class multiselect(Autocomplete):
    def widget(self, data=None):
        return f"""
            <div class="ac-widget">
                <input
                    name="ac-query"
                    placeholder="Start typing..."
                    hx-get="/autocomplete/multiselect/query/{data}"
                    hx-target="next .ac-results"
                    hx-swap="innerHTML"
                    hx-trigger="input changed delay:200ms, search"
                >
                <div class="ac-results">
                </div>
            </div>
            <div class="ac-hits">
            </div>
        """

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return ""
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return "".join(f'''<a
            class="clickable ac-result"
            hx-target="next .ac-hits"
            hx-swap="beforeend"
            hx-get="/autocomplete/multiselect/accept/{claim.id}"
        >{claim:label}</a>
        ''' for claim in claims)

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        return f"""
        <span class="ac-result">{claim}</span>
        <input type="hidden" name="value" value="{claim_id}">
        """


class merge(Autocomplete):
    def widget(self, data=None):
        return f"""
            <fieldset class="grid">
            <div class="ac-widget">
                <input
                    name="ac-query"
                    placeholder="start typing..."
                    hx-get="/autocomplete/merge/query/{data}"
                    hx-target="next .ac-results"
                    hx-swap="innerhtml"
                    hx-trigger="input changed delay:200ms, search"
                >
                <div class="ac-results">
                </div>
            </div>
            <div class="ac-widget">
                <input
                    name="ac-query"
                    placeholder="start typing..."
                    hx-get="/autocomplete/merge/query/{data}"
                    hx-target="next .ac-results"
                    hx-swap="innerhtml"
                    hx-trigger="input changed delay:200ms, search"
                >
                <div class="ac-results">
                </div>
            </div>
            </fieldset>
        """

    def get_results(self, query, connect):
        import veronique.objects as O
        if not query:
            return ""
        claims = O.Claim.search(
            q=query,
            page_size=5,
        )
        return "".join(f'''<a
            class="clickable ac-result"
            hx-target="closest .ac-widget"
            hx-swap="outerHTML"
            hx-get="/autocomplete/merge/accept/{claim.id}"
        >{claim:label}</a>
        ''' for claim in claims)

    def accept(self, claim_id):
        import veronique.objects as O
        claim = O.Claim(int(claim_id))
        return f"""
        <span class="ac-result">{claim}</span>
        <input type="hidden" name="value" value="{claim_id}">
        """
