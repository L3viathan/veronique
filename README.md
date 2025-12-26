# Véronique

_A small database for storing entities, links between them and simple
properties (e.g. text, color, numbers)._

![a screenshot showing a basic detail view of an example entry](screenshot.png)

Intended as a private social network/people database to help with memorizing
facts about people, but there's not really any features specific to that.

This is meant as a personal, intentionally non-scalable tool. As such, it uses
SQLite, and there's no proper packaging yet (mostly because it's not needed).
The app is protected from unauthenticated access, but beyond that there's no
protection against e.g. XSS. This is a feature, you can put HTML into text
fields for example. If you need SSO, MFA, or any other similar features, use a
different tool.

## Development

- Clone the repo
- Install `sanic`, `phonenumber`, and `markdown-it-py[linkify]` (to a venv)
- _Either_: Place a file called `veronique_initial_pw` containing a password in
  the working directory. This will be the password of the `admin` user.
- _Or_: Run `python -m veronique.bootstrap` to fill the database with testing
  data. The password of the admin user will be "admin". **This irrevocably
  overwrites any existing db you may have.**
- Run `sanic veronique:app --dev`

## Deployment

Running in production mostly means removing the `--dev` flag. Maybe set up a
systemd service for it and point a reverse proxy at it or something. I
personally [use
ansible](https://github.com/L3viathan/ansibly/blob/master/roles/mainserver/tasks/veronique.yml)
for deploying new versions.

Missing migrations are automatically applied when restarting the app.

## Concepts

The datatype starts mostly empty, only a few internal verbs are added during
the initial migration. There's also a fixed list of _data types_, since they
need supporting Python code.

### Claim

A claim can be thought of as a simple sentence: It (normally) has a subject, a
verb, and an object. For example, "John loves Mary", "Peter is 28 years old",
or "Paul knows that [John loves Mary]".

A subject is either another claim, or NULL. The latter is only possible when
the verb is a special builtin one called `ROOT`. Root claims have no subject
and no object and merely exist as markers for _something_; any kind of entity.

When you create a root claim, you also automatically create a second internal
claim of type `LABEL`, such that the thing you're creating has a name.

Now that we bootstrapped the world with root claims, we can talk about other
types of claims: They (non-root claims) always have a subject claim (which can
be, but doesn't have to be a root claim), a verb, and an object. The object can
either be another claim (when the verb has the data type `directed_link` or
`undirected_link`) or some atomic value (e.g. a number, a string, a date, ...).

### Verb

A verb has a similar function as it does in human language. You might also call
it a property or a predicate. A verb always has a label (what it's called, e.g.
`"loves"`), and a data type (see below). There's also a few built-in verbs that
get special treatment:

- `ROOT` and `LABEL` (as described above)
- `IS_A`: They have the data type `directed_link` and describe an is-a
  relation. You could for example create a root fact called `"human"` and link
  all people you create to it. There's special UI treatment for this relation
  (it's displayed in the heading of the claim detail view). A claim can have
  several `IS_A` links.
- `VALID_FROM` and `VALID_UNTIL`: They have the data type `date` and describe
  that a fact is only valid before or after a certain date. Invalid facts are
  visible as such in the frontend.
- `AVATAR`: A special field of type `picture` that will be used as the avatar
  for facts in their detail view and almost all other references to it.
- `COMMENT`: A regular `text` verb, except with special UI support.

### Data type

A data type describes what kind of object a claim of a certain verb can take.
Notable data types are:

- `directed_link`: This represents a regular link or transitive verb, e.g.
  `"loves"`, `"is child of"`, etc.
- `undirected_link`: These represent relationships that are by their nature
  undirected. You could use this for `"friend of"`, `"partner of"`, `"works
  with"`, or similar verbs, if you assume/model that this is never one-sided.
- `string`, `number`, `text`, `boolean`: As you might expect, these are fairly
  straightforward. Booleans get a checkbox as an input, string and text differ
  by the size of their input controls (regular input vs. textarea).
- `date`: Dates get special treatment in Véronique: You should enter them as
  `%Y-%m-%d` ISO timestamps, _but_ you are allowed to replace any digit with a
  question mark. This allows you to represent dates such as "some time in
  1973" or "26th of July, but I don't know which year", which can be common
  when entering data without full knowledge of the truth.
- `inferred`: This is a special type for which you can't create any actual
  claims. Instead, you need to define a set of rules by which this claim will
  automatically be shown on claim detail pages. As this sounds pretty abstract,
  here's an example: If you have a "child of" claim, you could create a
  "sibling" claim based on the fact that siblings always have a shared parent.

### Users

Véronique now has basic support for additional users. Non-admin users can by
default only see claims of a built-in type (e.g., root claims, labels,
category, ...).

You can then allow reading of other verbs per user, and also give _write_
access to certain verbs. Non-admin users can only create claims of those verbs
then, and can only edit claims they themselves have created.

Users can also be allowed to see a set of allowed queries. Pretty much anything
else is forbidden.
