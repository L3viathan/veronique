# Concepts

## Entities

An entity is something. A named thing. It could be a human, a place, an event;
anything you can give a name to.

An entity by itself has only a name (and an automatically assigned ID).

To create a new entity, select <kbd>New</kbd> &rarr; <kbd>Entity</kbd>. Then
enter a name (and optionally select a [category](#categories), more on that
later) and click the big submit button:

![Creating a new entity](img/new-entity.png)

You'll end up on the page of this entity, which will look pretty empty for now.

## Verbs

Verbs connect let you connect entities (and claims) with other entities (and
claims), _or_ with data. A verb also has a name, like "loves" or "lives in" or
"was born on", and a [type](data-types.md).

To create a new verb, select <kbd>New</kbd> &rarr; <kbd>Verb</kbd>. Next, enter
a name, and select the type. For now, let's select `directed_link`, which links
two entities (or other claims):

![Creating a new verb](img/new-verb.png)

## Claims

Finally, we can combine entities and verbs into _claims_.

A claim can be thought of as a simple sentence:

![Bart Simpson — lives in — Springfield](img/claim-relation.png)

It has a subject (the entity "Bart Simpson"), a verb ("lives in"), and an
object (the entity "Springfield"). Sometimes the object is not an entity, but
plain data, [which can take many different forms](data-types.md):

![Homer Simpson — full name — Homer Jay Simpson](img/claim-plain.png)

To create a claim, click on the plus button on one of the sides of an entity
page, then start typing the name of the other entity until you see it and click
on it:

![Making the Homer Simpson — child of — Abraham Simpson claim](img/new-relation.png)

Which side you choose determines whether this entity will be the subject or the
object of the claim.

### Categories

You may want to add different _kinds_ of things into your Véronique database.
To facilitate this, there's a built-in verb called `category` that gets special
UI support.

A category is nothing special, it's just another entity.

To mark something as a category, click on the little plus under the heading of
an entity page that represents one of its members and start typing the name of
the category.

![Setting a category](img/set-category.png)

Once something is a category of another entity, you will be able to select it
as the category of an entity when creating a new entity (it will appear in the
dropdown input). Choose your first category wisely, as it will be the category
that will be selected by default when creating a new claim. The author of this
document uses "human" as the default category.
