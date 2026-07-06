# Administration

## Settings

...

## Users

You can add any amount of additional users
(<kbd>New</kbd>&rarr;<kbd>User</kbd>). In addition to a name, you can give the
new user permissions of three varieties:

- **Readable verbs:** The user will be able to see claims of these types.
- **Writable verbs:** The user will be able to create new claims of these
  types, and edit _their own_ claims of these types. They are never able to
  edit other users' claims. If you want the user to be able to create entities,
  you need to grant them write permissions for _both_ `root` and `category`.
- **Viewable queries:** The user may see these queries. Other users are never
  able to create new queries, as that would effectively grant them admin
  permissions.

Other users are never able to

- create verbs — this is the responsability of the admin(s).
- create queries — as mentioned above, this would be exploitable.
- create users

It is currently not possible to add additional admin users.

There's also an option to "redact PII" for this user, which will result in all
variable data being censored. This exists mainly to demonstrate how Véronique
works without needing to fill it with fake data. Bear in mind that this will
_still_ show non-textual data (such as dates) and will allow inferring PII via
metadata and links.
