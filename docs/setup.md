# Installing Véronique

To run Véronique, you need [Python](https://python.org). It is recommended to
use virtual environments. Opinions and preferences on virtual environments
differ, use your preferred tooling.

If you wish to install the latest release, you can now simply `pip install
veronique`.

If you want to run from the latest version on Github, clone the repository
instead and install Véronique's dependencies (if you use something like `uv`
you can skip this step, as it will automatically install dependencies when
starting the application).

## Initial setup

Before you can start Véronique for the first time, you need to generate a
password and put it in a file called `veronique_initial_pw` in the directory
from which you start Véronique. The file will be deleted on first startup, so
save it somewhere.

## Starting Véronique

Véronique uses [sanic](https://sanic.dev/), you therefore have to run `sanic
run veronique` to start the application. For production use you will want to
put this inside a unit file, or a container, or some other supervisor thing.

Once Véronique is up and running, you can visit it at http://localhost:8000.
For production use you will want to not make this publicly accessible and hide
behind a reverse proxy that deals with SSL.

Of course you can also just run Véronique on your local machine, then you don't
have to worry about all that.

## Data and backups

All data is stored in the SQLite DB contained in `veronique.db`. It is enough
to create backups of this file.

### Exception: `file`

The file contents of `file` verbs are instead stored on disk. This only works
if you set the environment variable `VERONIQUE_USER_CONTENT_PATH` to something
(or create a `user-content` directory/symlink in the working directory of the
web service).
