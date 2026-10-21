from veronique.html import H


def TEMPLATE(title, news, gotos, user, content, errors):
    return H(
        "<!DOCTYPE html>",
        H.html(
            H.head(
                H.script("", src="/static/htmx.js"),
                H.title(title),
                H.link(rel="stylesheet", href="/static/style.css"),
                H.link(rel="stylesheet", href="/static/mana-cost.css"),
                H.link(rel="stylesheet", href="/static/pico.min.css"),
                H.link(rel="stylesheet", href="/static/prism.css"),
                H.link(rel="stylesheet", href="/static/leaflet.css"),
                H.meta(name="htmx-config", content='{scrollIntoViewOnBoost": false}'),
                H.script("", src="/static/sigma.min.js"),
                H.script("", src="/static/graphology.umd.min.js"),
                H.script("", src="/static/graphology-library.min.js"),
                H.script("", src="/static/prism.js"),
                H.script("", src="/static/leaflet.js"),
                H.script("""
                    function update(text) {
                      let result_element = document.querySelector("#highlighting-content");
                      // Handle final newlines (see https://css-tricks.com/creating-an-editable-textarea-that-supports-syntax-highlighted-code/)
                      if(text[text.length-1] == "\n") {
                        text += " ";
                      }
                      result_element.innerHTML = text.replace(new RegExp("&", "g"), "&amp;").replace(new RegExp("<", "g"), "&lt;");
                      Prism.highlightElement(result_element);
                    }

                    function sync_scroll(element) {
                      /* Scroll result to scroll coords of event - sync with textarea */
                      let result_element = document.querySelector("#highlighting");
                      // Get and set x and y
                      result_element.scrollTop = element.scrollTop;
                      result_element.scrollLeft = element.scrollLeft;
                    }
                """),
            ),
            H.body(
                H.header(
                    H.nav(
                        H.ul(
                            H.li(
                                H.a(
                                    H.img(id="logo", src="/static/veronique.svg", alt="Logo"),
                                    "/",
                                ),
                            ),
                        ),
                        H.ul(
                            news,
                            H.li(
                                H.details(
                                    H.summary(
                                        H.span("Go to...", cls="no-mobile"),
                                        H.span("Go", cls="mobile-only"),
                                    ),
                                    H.ul(
                                        *gotos,
                                        dir="rtl",
                                    ),
                                    cls="dropdown",
                                ),
                            ),
                            H.li(
                                H.input(
                                    id="q",
                                    name="q",
                                    type="search",
                                    hx_get="/search",
                                    hx_trigger="input changed delay:200ms, search",
                                    hx_select="#container",
                                    hx_target="#container",
                                    hx_push_url="true",
                                ),
                            ),
                            user,
                        ),
                    ),
                ),
                H.main(
                    content,
                    id="container",
                ),
                errors,
            ),
            data_theme="light",
        ),
    )


def LOGIN(then):
    return H(
        "<!DOCTYPE html>",
        H.html(
            H.head(
                H.script("", src="/static/htmx.js"),
                H.title("Login — Véronique"),
                H.link(rel="stylesheet", href="/static/style.css"),
                H.link(rel="stylesheet", href="/static/pico.min.css"),
                H.meta(name="htmx-config", content='{scrollIntoViewOnBoost": false}'),
            ),
            H.body(
                H.header(
                    H.nav(
                        H.ul(
                            H.li(
                                H.a(
                                    H.img(id="logo", src="/static/veronique.svg", alt="Logo"),
                                    href="/",
                                ),
                            ),
                        ),
                    ),
                ),
                H.main(
                    H.article(
                        H.header(H.h3("Login")),
                        H.form(
                            H.fieldset(
                                H.label(
                                    "Username",
                                    H.input(name="username", placeholder="username"),
                                ),
                                H.label(
                                    "Password",
                                    H.input(type="password", name="password", placeholder="password"),
                                ),
                            ),
                            H.input(type="hidden", name="then", value=then),
                            H.input(type="submit", value="Login"),
                            action="/login",
                            method="POST",
                        ),
                    ),
                    id="container",
                ),
            ),
            data_theme="light",
        ),
    )
