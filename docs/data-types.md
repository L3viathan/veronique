# Data types

Verbs can have many different types:

## `directed_link`

This represents a directed relation between two claims/entities. This will be
most kinds of relations, but it requires a directionality, i.e., "child of",
"lives in", etc.

## `undirected_link`

Where relations are between equal members ("partner of", "friend of", "works
with"), you want to use the `undirected_link` type instead. These will look
identical from either side.

## `inferred`

Inferrable verbs are special in that you never explicitly create any claims for
them. Instead, they get shown automatically when a set of conditions is
fulfilled. The prime example of this would be a "sibling" or "grandparent"
relation — you can define it by a combination of other relations.

Peter is a grandparent of Mary if there's another person whos the parent of
Mary and the child of Peter:

![Creating an inferred verb](img/new-inferred-verb.png)

After entering a name and selecting `inferred` as the type, you'll need to
define what it means by "this" (your subject) being in that relation with
"that" (your object). To define the relation, you'll need additional helper
claims (a "parent" in both of the examples above). Every row needs to hold for
the relation to exist. Click the <kbd>+</kbd> button to create a new row, and
fill in each input to the desired value. "A", "B", and so on are these helper
claims.

## `string`

A simple, short text. Use this for things that would usually fit in one line.

## `text`

Behaves mostly like `string`, but you'll have a multiline input, and the output
renders as Markdown.

## `number`

Another one in the group of very simple types. This represents a number that
will usually not change. For ages theres a [dedicated type](#age).

## `color`

To be honest, I don't know if this is ever useful, but it was just easy to
create. Maybe for "hair color" or "favourite color" or "corporate design
primary color" or something like that.

## `date`

Véronique has special support for dates. There's three ways in which you can
enter them:

- If you know the day and month, but not the year, you can provide the date in
  the format `mm-dd` (e.g. "02-13").
- If you only know the year, but not day or month, simply enter the four-digit
  year.
- If you know the exact date, use the full ISO 8601 format of `YYYY-mm-dd`
  (e.g. "2025-02-13").
- Finally, you can use any of the above formats and replace one or more digits
  with a question mark to indicate lack of knowledge. For example, `06-??`
  represents "some time in June some year". You may even just provide a single
  "?" (for "completely unknown date"), but that is rarely useful.

When displaying a date, Véronique compares it with the current date and shows a
human-readable diff:

![1855-07-06, showing as "in 3 days, 171 years ago"](img/date-display.png)

## `boolean`

A simple boolean (true/false) input. Shown as a checkbox.

## `location`

## `email`

## `website`

## `phonenumber`

## `picture`

## `social`

## `mtgcolors`

## `alpha2`

## `age`

## `choice`

## `choices`
