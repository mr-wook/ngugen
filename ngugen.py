#!/bin/env python3
"ngugen -- generate nginx.unit config files, safely and sanely via a tiny DSL;"

if True:
    from   collections import OrderedDict # To make things look 'right';
    import json
    import os
    import re

    __author__    = "mr.wooK@gmail.com"
    __license__   = "MIT License"
    __copyright__ = "2021 (c)"

    DEBUG = False

    """
    # Routes
                  { "match": { "uri": [ "/v1" ]}, "action": { "pass": "applications/error_v1" } },
                  { "match": { "uri": [ "/search", "/esearch", "/search/v0", "/search/v1" ] } }
                  { "match": { "uri": [ "/dummy/v0" ] }, "action": { "pass": "applications/dummy_v0" } },
                  { "match": { "uri": [ "/dummy" ] }, "action": { "pass": "applications/dummy_app" } },
                  { "action": { "pass": "applications/search" } },
    Applications
        "error_v1": {
          "type": "python3.8",
          "user": "nobody",
          "path": "/var/www/unit/applications/error_server",
          "module": "error_server",
          "working_directory" : "/tmp",
          "processes" : {
            "max": 3,
            "spare": 2
          },
          "environment": {
            "aws_access_key_id":"x",
            "aws_secret_access_key":"y"
            }
        },
    ,
        "dummy_app": {
              "type": "python3.8",
              "working_directory": "/var/app/error_service",
              "path": "/var/www/unit/applications/error_server",
              "module": "dummy_server"
        },
        "dummy_v0": {
              "type": "python3.8",
              "working_directory": "/var/app/error_service",
              "path": "/var/www/unit/applications/error_server",
              "module": "dummy_server"
        },


    ____________________________________________________________________________
    % ngugen <conf_file>
    : show -- show file as conf
    : jq -- show via jq
    : q
    : write <conf_file>.json
    : !param spec (as below)
    : update <conf_file>

    """

class Ngugen():
    ASSIGNMENT = re.compile(r'(?P<lhs>[\w\.\"]+)\s*=\s*(?P<rhs>.*)')
    INCLUDE = re.compile(r'^include\s+(?P<filename>[\w\.\/]+)')
    LISTENERS = re.compile(r'^listeners\s+(?P<domains>.*):(?P<port>\d+)\s+(?P<processor>.*)')
    ROUTES = re.compile(r'^routes\s+(?P<matcher>\w+)\s*(?P<processor>[a-z]+)\s*(?P<application>\w+)\s*(?P<targets>.*)')

    def __init__(self, cfg_file = None):
        self._fn = cfg_file
        self._globals = dict(applications=dict(), listeners=dict(), routes=dict(),
                             settings=dict(), isolation=dict(), extras=dict())
        self._listeners = {}
        self._applications = {}
        self._isolation = {}
        self._routes = [ ]
        self._settings = {}
        self._extras = {}
        self._top = { "global" : self._globals, "apps" : self._applications,
                      "applications" : self._applications,
                      "listeners" : self._listeners, "routes" : self._routes,
                      "settings": self._settings, "isolation" : self._isolation,
                      "extras" : self._extras }
        self._sequence = [ 'listeners', 'routes', 'applications', 
                           'settings', 'isolation', 'extras' ]
        if cfg_file:
            self.load(cfg_file)

    def parse_line(self, ln):
        ln = ln.strip()
        match = Ngugen.ASSIGNMENT.match(ln)
        if match:
            gd = match.groupdict()
            return self._assign(gd['lhs'], gd['rhs'])
        match = Ngugen.INCLUDE.match(ln)
        if match:
            gd = match.groupdict()
            return self._include(gd['filename'])
        match = Ngugen.LISTENERS.match(ln)
        if match:
            gd = match.groupdict()
            return self._listener(gd['domains'], gd['port'], gd['processor'])
        match = Ngugen.ROUTES.match(ln)
        if match:
            gd = match.groupdict()
            if gd['processor'] == "default":
                targets = ""
            else:
                targets = gd['targets']
            return self._routing(gd['matcher'], gd['processor'], gd['application'], targets)
        return False

    def load(self, fn):
        ifd = open(fn, 'r')
        ibuf = [ln[:-1].strip() for ln in ifd.readlines()]
        ifd.close()
        ibuf = [ln for ln in ibuf if ln]
        ibuf = [ln for ln in ibuf if not ln[0] in [ '#', ';' ] ]
        self._ibuf = ibuf
        load_ok = True
        for ln in self._ibuf:
            self.debug(f"--{ln}--")
            rc = self.parse_line(ln)
            if not rc:
                print(f"Parse failed for {ln}")
                load_ok = False
        return load_ok

    def _assign(self, lhs, rhs):
        self.debug(f"_assign: {lhs} {rhs}")
        lhs, rhs = lhs.strip(), rhs.strip()
        if lhs != lhs.lower():
            print("WARNING: assignment: left hand side {lhs} is not all lower case")
        if '"' in lhs:
            lhs_split = self._assignment_quoted(lhs)
            if not lhs_split:
                raise ValueError(f"Bad quotes in assignment in {lhs}")
        else:
            lhs_split = lhs.split('.')
        if len(lhs_split) < 2:
            raise ValueError(f"Bad assignment destination in {lhs}")
        group = lhs_split.pop(0).lower()
        if group not in self._top:
            raise ValueError(f"Unknown assignment group {group}")
        domain = self._top[group]
        while lhs_split:
            pointer = lhs_split.pop(0)
            if lhs_split and (pointer in domain):
                domain = domain[pointer]
                continue
            # if more things in vector but pointer not established in domain, establish it;
            if lhs_split and (pointer not in domain):
                domain[pointer] = dict()
                domain = domain[pointer]
                continue
            # Check for terminal pointer, and make assignment
            if (not lhs_split) and pointer:
                domain[pointer] = rhs
                return True
            # if not lhs_split, should have done assignment by now?
            raise ValueError(f"Termination issues in assignment for {lhs} = {rhs}")

    def _assignment_quoted(self, lhs):
        lhs_split = [ ]
        while lhs:
            if not lhs.startswith('"'):
                if '.' in lhs:
                    dot = lhs.index('.')
                    lhs_split.append(lhs[:dot])
                    lhs = lhs[dot + 1:]
                    continue
                # Terminal word
                lhs_split.append(lhs)
                return lhs_split
            # lhs must start with '"' by now;
            if lhs.count('"') & 1:
                raise ValueError(f"Odd number of quotes in {lhs}")
            q0 = 0                              # Skip the first quote...
            q1 = lhs.index('"', q0 +1 )
            # q1 = lhs[q0+1:lhs.index('"') + 1]   # Get everything between the quotes...
            field = lhs[q0 +1:q1]
            lhs = lhs[len(field) + 3:]          # Lose dot + what's been parsed before next iteration;
            lhs_split.append(field)
            continue
        return lhs_split

    def debug(self, txt):
        if DEBUG:
            print(txt)
        return True

    def _include(self, fn):
        self.debug(f"_include {fn}")
        self._load(fn)
        return True

    def _listener(self, domains, port, processor):
        """
            Listeners are a dict of key-value pairs where the key is
            "hostnames:portnums and the value is a dictionary of pass options;
        """
        group = self._top['listeners']
        domain_port = f"{domains}:{port}"
        action, where = re.split(r'\s+', processor)
        group[domain_port] = { action : where }
        return True

    def _routing(self, matcher, processor, app, targets):
        """
            routes are a list of dicts, where match provides a predicate condition
            (ie: uri against a list of potential matches), with a final action case that provides
            the default route if none of the prior matches succeeds;
        """
        routes = self._top['routes']
        matcher, processor = matcher.lower(), processor.lower()
        if matcher == "match_uri":
            targets = targets.replace(",", " ")
            uri_list = re.split(r'\s+', targets)
            pass_dict = { processor : app }
            route = dict(match=OrderedDict(uri=uri_list, action=pass_dict))
            routes.append(route)
            return True
        elif matcher == "default":
            route = dict(action={ processor : app })
            routes.append(route)
            return True
        else:
            raise ValueError(f"Unknown processor type {processor}")
        return True

    def save(self, fn):
        if os.path.isfile(fn):
            os.rename(fn, f"{fn}~")
        ofd = open(fn, 'w')
        top = dict()
        final = dict()
        for section in self._sequence:
            user_globals = self._globals[section]
            specified = self._top[section]
            if section == 'routes':
                top[section] = specified
                continue
            elif section == 'extras':
                top.update(self._top[section])
                continue
            elif not self._top[section]:
                continue
            elif section == 'applications':
                if not self._top[section]:
                    continue
                top[section] = dict()
                subsections = list(self._top[section].keys())
                subsections.sort()
                for sub in subsections:
                    per_app = self._top[section][sub]
                    use = { **user_globals, **per_app }
                    top[section][sub] = use
                continue
            else:
                top[section] = { **user_globals, **specified}
                continue
        output = json.dumps(top, indent=2)
        ofd.write(f"{output}\n")
        ofd.close()
        return True

if __name__ == "__main__":
    import sys

    args = sys.argv[:]
    pname = args.pop(0)
    if not args:
        print(f"No filename on command line, that's all folks!")
        sys.exit(1)
    ifn = args.pop(0)
    if not os.path.isfile(ifn):
        print(f"File {ifn} not found, ttfn!")
        sys.exit(1)
    if args:
        ofn = args.pop(0)
    else:
        ofn = os.path.splitext(ifn)[0] + ".json"
    ngugen = Ngugen(ifn)
    ngugen.save(ofn)
    print(f"Wrote {ofn}")

