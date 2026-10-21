import html
from functools import partial


class Tag:
    def __init__(self, tag, *children, **attributes):
        self.tag = tag
        self.children = children
        self.attributes = {
            k.replace("__", ":").replace("_", "-"): v
            for k, v in attributes.items()
        }
        if "cls" in self.attributes:
            self.attributes["class"] = self.attributes.pop("cls")

    def __str__(self):
        return "".join(self.serialize())

    def serialize(self):
        if self.tag is not None:
            yield f"<{self.tag}"
            for attribute, value in self.attributes.items():
                if isinstance(value, bool):
                    if value:
                        yield f" {attribute}"
                elif value is None:
                    continue
                else:
                    try:
                        yield f' {attribute}="{html.escape(value)}"'
                    except Exception as e:
                        raise RuntimeError(f"Bad attribute {attribute!r}: {value!r})") from e
            yield ">"
        for child in self.children:
            if child is None:
                # This allows easy optional elements
                continue
            elif isinstance(child, Tag):
                yield from child.serialize()
            else:
                yield child  # strings
        if self.children and self.tag is not None:
            yield f"</{self.tag}>"


@type.__call__
class H:
    def __getattr__(self, tag):
        return partial(Tag, tag)

    def __call__(self, *children):
        """
        This is used for simple grouping without a real tag. We return a
        pseudo-tag None, which can't otherwise exist.
        """
        return Tag(None, *children)


def join(joiner, joinees):
    yielded = False
    for joinee in joinees:
        if yielded:
            yield joiner
        yield joinee
        yielded = True
