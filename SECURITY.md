# Reporting a Vulnerability

If you found a vulnerability, I would appreciate disclosing it in private by sending an email to security at l3vi dot de.

## What's in scope

- As an unauthenticated user: Gaining any access to sensitive data.
- As an authenticated, regular user:
  - Reading claims that the user has no permissions for.
  - Creating claims that the user has no permissions for.
  - Editing or deleting claims that the user doesn't own.
 
## What's NOT in scope

- As an admin, doing anything nefarious.
