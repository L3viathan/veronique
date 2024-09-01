# Véronique

A small database for storing entities, links between them and simple properties
(e.g. text, color, numbers). Intended as a private social network/people
database to help with memorizing facts about people, but there's not really any
features specific to that.

This is meant as a personal, intentionally non-scalable tool. As such, it uses
SQLite, and there's no proper packaging yet (mostly because it's not needed).
The app is protected by basic auth, but beyond that there's no protection
against e.g. XSS. This is a feature, you can put HTML into text fields for
example. If you need multiple users, SSO, MFA, or any other similar features,
use a different tool.

## Development

- Clone the repo
- Install `sanic` (to a venv)
- Run `VERONIQUE_CREDS='foo:bar' sanic api --dev`

## Deployment

Running in production mostly means replacing the `VERONIQUE_CREDS` with some
random values, and removing the `--dev` flag. Maybe set up a systemd service
for it and point a reverse proxy at it or something. I personally [use
ansible](https://github.com/L3viathan/ansibly/blob/master/roles/mainserver/tasks/veronique.yml)
for deploying new versions.

Missing migrations are automatically applied when restarting the app.

## Concepts

The database starts empty without any entity types, entities, properties, or
facts. _Data types_ exist however, because they need supporting Python code.

### Entity types

An entity type is a type of entity, duh. You could start with **human**,
**place**, and **company**.

### Entities

An entity is an _instance_ of an entity type. If you have an entity type called
**human**, "Steve from Accounting" could be an entity of type **human**.

### Properties

A property is a named link between an entity (of a specific type) and either
another entity (of another specific type) or a plain value (more on that
later). When creating a new property, you first have to choose the subject type
(e.g. **human**), the label (e.g. "reports to") and the property type.

If you select "entity" for the latter, this property will allow links between
two entities. You now have to make two more choices: What object type (as in:
grammatical object) the property has, and the type of _reflectivity_. We'll get
back to that concept later.

Otherwise (if you select anything else as the property type), you end up with a
property that allows attaching plain (meaning: not links _between_ entities)
values of various _data types_ to an entity.

### Data types

There is a fixed list of data types, which can only get extended by writing
Python code. These support the aforementioned plain property types. Examples
for data types would be "string", "color", or "date", and each of them displays
differently later. They also dictate how values can be edited (basically which
HTML `<input>` type they map to), and how values are (de-)serialized from and
to the database.

### Facts

Facts are triples of (entity, property, value), at least conceptually. If
"Steve from accounting" is an entity, and "birthday" is a property of type
(human-&gt;date), then you can add a fact to Steve that says that _his_
birthday is on the 23rd of April 1984. If the property of a fact is a link, it
could claim that Steve reports to Katy.

### Reflectivity

When creating a link (a property of type entity), you have to choose between
three types of reflectivity: unidirectional, self-reflected, or reflected.
A _unidirectional_ property has no implications for the target of a link.  
A _self-reflected_ property means that when you create a link from A to B, a
corresponding link from B to A will also be created. This could for example be
used for a property called "is married to".  
Finally, a _reflected_ property will prompt for a second property name; the one
of the counterpart of this property. For example, you could create a reflected
property called "is parent of", and give the counterpart the label "is child
of".

When deleting a fact of a non-unidirectional property, the matching fact of the
object is also deleted. When _editing_ (i.e. re-linking) such a fact, the old
reflected fact will be deleted and a new one created. These two facts are
essentially treated as a single fact.
