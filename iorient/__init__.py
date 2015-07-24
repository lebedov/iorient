#!/usr/bin/env python

# Copyright (c) 2015, Lev Givon
# All rights reserved.
# Distributed under the terms of the BSD license:
# http://www.opensource.org/licenses/bsd-license

import pprint
import re

from IPython.core.magic import Magics, magics_class, line_magic, cell_magic
from IPython.config.configurable import Configurable

import prettytable
import pyorient
import truncate

def show_json(results):
    """
    Display results using prettyprint.
    """

    for r in results:
        pprint.pprint(r)

def show_table(results, max_len=25):
    """
    Display results of PyOrient query as a table.
    """

    cols = set()
    for r in results:
        cols.update(r.keys())
    p = prettytable.PrettyTable(cols)
    for r in results:
        row = []
        for k in cols:
            if r.has_key(k):
                if type(r[k]) == pyorient.types.OrientBinaryObject:
                    s = '<OrientBinaryObject @ %s>' % hex(r[k].__hash__())
                elif type(r[k]) == pyorient.types.OrientRecordLink:
                    s = '%s' % r[k].get_hash()
                else:
                    s = str(r[k])
            else:
                s = ''
            if len(s) < max_len:
                row.append(s)
            else:
                row.append(truncate.trunc(s, 0, max_len))
        p.add_row(row)
    print p

def parse(cell, self):
    # Set posix=False to preserve quote characters:
    opts, cell = self.parse_options(cell, 'j', posix=False)

    server = 'localhost'
    db_name = ''
    port = 2424
    user = ''
    passwd = ''
    cmd = ''
    is_query = False
    
    # Split the line/cell contents into a first string and a remainder:
    parts = [part.strip() for part in cell.split(None, 1)]

    if parts:

        # user[:password]@server_and_db_string
        r = re.search('^([^:]+)(?::([^:]+))?@(.+)$', parts[0])
        if r:
            new_user, new_passwd, tmp = r.groups()
            if new_user:
                user = new_user
            if new_passwd:
                passwd = new_passwd
            r = re.search('^([^:/]+)(?::(\d+))?(?:/([^:/]+))?$', tmp)
            if r:
                new_server, new_port, new_db_name = r.groups()

                # user[:password]@db_name
                if not new_port and not new_db_name:
                    db_name = new_server

                # user[:password]@server[:port]/db_name
                else:
                    if new_server:
                        server = new_server
                    if new_port:
                        port = int(new_port)
                    if new_db_name:
                        db_name = new_db_name

            # Query to execute:
            if len(parts) > 1:
                cmd = parts[1]
        else:
        
            # No connect string specified:
            cmd = cell
    else:

        # No connect string specified:
        cmd = cell

    if re.search('^select .*', cmd):
        is_query = True

    return {'server': server, 'db_name': db_name, 'port': port,
            'user': user, 'passwd': passwd, 'cmd': cmd, 'is_query': is_query}

@magics_class
class OrientMagic(Magics, Configurable):

    # Database connections; keys are "user@db_name":
    db = {}
    last_key = ''

    @line_magic
    @cell_magic
    def orient(self, line, cell=''):
        """
        Runs an OrientDB SQL query against an OrientDB database.

        Multiple database connections are supported. Once a connection has been
        established, it can be used by specifying its user@dbname. If no connect
        string is specified after at least one connection has been
        established, the most recently used connection will be used to execute
        the query.

        Examples
        --------
        %orient user:passwd@server/dbname

        %orient user:passwd@server:2424/dbname

        %%orient user@dbname
        select from v
        """

        parsed = parse('%s\n%s' % (line, cell), self)

        if parsed['user'] and parsed['db_name']:
            key = parsed['user']+'@'+parsed['db_name']
            self.last_key = key
        else:
            key = self.last_key

        if key in self.db:
            client = self.db[key]
        else:
            client = pyorient.OrientDB(parsed['server'], parsed['port'])
            client.connect(parsed['user'], parsed['passwd'])
            client.db_open(parsed['db_name'], parsed['user'], parsed['passwd'])
            self.db[key] = client

        if parsed['cmd']:
            if parsed['is_query']:
                results = client.query(parsed['cmd'])
                return [r.oRecordData for r in results]
            else:
                client.command(parsed['cmd'])

    @line_magic
    def oview(self, line):
        """
        View results of OrientDB query.

        Examples
        --------
        # Display results as table:
        r = %orient select from v
        %oview r

        # Display results using pretty print:
        %oview -j r

        # Display several results variables consecutively:
        a = %orient select from v where x < 3
        b = %orient select from v where y > 4
        %oview a b
        """

        # Set posix=False to preserve quote characters:
        opts, line = self.parse_options(line, 'j', posix=False)

        results = [self.shell.user_ns[r] for r in line.split()]
        if opts.has_key('j'):
            for r in results:
                show_json(r)
        else:
            for r in results:
                show_table(r)
        
    def __del__(self):

        # Cleanly shut down all database connections:
        for client in self.db:
            client.db_close()

def load_ipython_extension(ip):
    ip.register_magics(OrientMagic)

