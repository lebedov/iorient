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

def orientrecord_to_dict(r):
    """
    Convert a pyorient.types.OrientRecord into a dict.
    """

    out = {}
    out['class'] = r._class
    out['rid'] = r._rid
    out['version'] = r._version
    storage = {}
    if r.oRecordData:
        for k in r.oRecordData:
            if isinstance(r.oRecordData[k],
                    pyorient.types.OrientRecordLink):
                storage[k] = r.oRecordData[k].get_hash()
            else:
                storage[k] = r.oRecordData[k]
    out['storage'] = storage
    return out

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
    opts, cell = self.parse_options(cell, 'g', posix=False)

    server = 'localhost'
    db_name = ''
    port = 2424
    user = ''
    passwd = ''
    cmd = ''
    cmd_type = 'cmd'

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

    if opts.has_key('g'):
        cmd_type = 'gremlin'
    elif re.search('^select .*', cmd):
        cmd_type = 'query'
    else:
        cmd_type = 'cmd'

    return {'server': server, 'db_name': db_name, 'port': port,
            'user': user, 'passwd': passwd, 'cmd': cmd, 
            'cmd_type': cmd_type}

@magics_class
class OrientMagic(Magics, Configurable):

    # Database connections; keys are "user@db_name":
    db = {}
    last_key = ''

    @line_magic
    @cell_magic
    def orient(self, line, cell=''):
        """
        Runs an OrientDB query against an OrientDB database.

        Multiple database connections are supported. Once a connection has been
        established, it can be used by specifying its user@dbname. If no connect
        string is specified after at least one connection has been
        established, the most recently used connection will be used to execute
        the query.

        Queries are assumed to be in OrientDB SQL. Gremlin queries 
        may be run by specifying the -g option.

        Query results are returned as a list of dictionaries.

        Examples
        --------
        %orient user:passwd@server/dbname

        %orient user:passwd@server:2424/dbname

        %%orient user@dbname
        select from v

        %orient -g user@dbname g.V.has('name', 'foo')
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
            if parsed['cmd_type'] == 'gremlin':

                # Try wrapping Gremlin queries in a pipeline and/or closure to
                # convert the results to ODocument instances (if possible) so as
                # to prevent serialization failure; see http://bit.ly/1hhm06F
                cmd = """
def make_doc = {x -> new com.orientechnologies.orient.core.record.impl.ODocument(x)};
p = { -> %s}; result = p();
try {make_doc(result)}
catch (all) {
if (result instanceof GremlinPipeline){
    result.transform{try {make_doc(it)} catch (a0) {it}}}
else if (result instanceof Iterable) {
    try {(new GremlinPipeline()).start(result)}
    catch (a1) {result}}
else {
     (new GremlinPipeline()).start(result).transform{try {make_doc(it)} catch (a2) {it}}}
}
""" % parsed['cmd']
                results = client.gremlin(cmd)
                return [orientrecord_to_dict(r) if isinstance(r,
                        pyorient.types.OrientRecord) else r for r in results]
            elif parsed['cmd_type'] == 'query':
                results = client.query(parsed['cmd'])
                return [orientrecord_to_dict(r) if isinstance(r,
                        pyorient.types.OrientRecord) else r for r in results]
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

        # Set maximum length at which to truncate individual fields:
        %oview -t 100 r

        # Display results using pretty print:
        %oview -j r

        # Display several results variables consecutively:
        a = %orient select from v where x < 3
        b = %orient select from v where y > 4
        %oview a b
        """

        # Set posix=False to preserve quote characters:
        opts, line = self.parse_options(line, 'jt:', posix=False)

        results = [self.shell.user_ns[r] for r in line.split()]
        if opts.has_key('j'):
            for r in results:
                show_json(r)
        elif opts.has_key('t'):
            try:
                max_len = int(opts['t'])
            except:
                raise ValueError('integer expected')
            else:
                for r in results:
                    show_table(r, max_len)
        else:
            for r in results:
                show_table(r)

    def __del__(self):

        # Cleanly shut down all database connections:
        for client in self.db:
            client.db_close()

def load_ipython_extension(ip):
    ip.register_magics(OrientMagic)
