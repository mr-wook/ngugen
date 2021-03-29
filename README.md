# ngugen
ngugen is used to build nginx.unit configurations out of a simple domain specific language (DSL)

## Why?

I was building a small microService ecology recently, and found one of the biggest
unanticipated time sucks was modifying and debugging the JSON file that contained
the nginx.unit configuration, which I was modifying at a relatively high frequency.

Part of the reason is that you can't comment anything out of a strict JSON source.
Another part was that the layout of some parts (like ROUTES) made for low readability,
given the sometimes predicate nature of the arguments.

## What?

While the source code is structured as a simple CLI app that leverages a single
class to do all the work, it can be used in other applications as well (perhaps rolled into a more complex UI that does the generate/transmit/report loop), since nginx.unit has a long way to go to provide detailed error reporting on config, or even application errors.

### Examples
```
# Put before overrides;
# include <base_conf_file>

# Comments at BOL only
# Quoting is implicit;
global.applications.user = nobody
global.applications.type = python3.8
global.applications.path = /var/www/unit/applications/error_server
global.applications.processes.max = 3
global.applications.processes.spare  = 2
global.applications.working_directory /tmp

# Extras are always tacked on before the final close
extras.access_log = /var/log/nginx_unit_access.log

# Listeners are always stored first
listeners  *:5000 pass routes

# Routes are always stored after listeners
#  Sequencing of routes is important here, the routes are stored
#  in order;
routes match_uri pass applications/error_v1  /v1
routes match_uri pass applications/dummy_v0  /dummy/v0
routes match_uri pass applications/dummy_app  /dummy
routes match_uri pass applications/search  /search, /esearch, /esearch/v0, /esearch/v1
routes default   pass applications/error_v1

# Applications apply globals per domain, and are applied before config data (so they can be overriden)
# Applications are stored after routes;

# listeners "*:80" pass:applications/$host

applications.error_v1.module=error_server
applications.error_v1.environment.aws_access_key_id=foo
applications.error_v1.environment.aws_secret_access_key=bar
applications.dummy_app.module=dummy_server
applications.dummy_app.processes.max = 1
applications.search.module=error_search
applications.error_admin.callable=app
```