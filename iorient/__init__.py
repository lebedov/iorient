#!/usr/bin/env python

# Copyright (c) 2015, Lev Givon
# All rights reserved.
# Distributed under the terms of the BSD license:
# http://www.opensource.org/licenses/bsd-license

import pprint
import re

import IPython
from IPython.core.magic import Magics, magics_class, line_magic, cell_magic

if IPython.release.version < '4.0.0':
    from IPython.config.configurable import Configurable
else:
    from traitlets.config import Configurable

try:
    from pyorient.types import OrientBinaryObject, OrientRecordLink
except ImportError:
    from pyorient.otypes import OrientBinaryObject, OrientRecordLink 

import prettytable
import pyorient
import truncate

def _iterable(x):
    try:
        iter(x)
    except:
        return False
    else:
        return True

def orientrecord_to_dict(r):
    """
    Convert a pyorient.otypes.OrientRecord into a dict.
    """

    # Recurse into dictionary replacing OrientRecordLink objects with their RIDs
    # and removing OrientBinaryObjects:
    def rec(d):
        if isinstance(d, dict):
            out = {}
            for k in d:
                if not isinstance(d[k], OrientBinaryObject):
                    out[k] = rec(d[k])
            return out
        elif _iterable(d) and not isinstance(d, basestring):
            return d.__class__(map(rec,
                [x for x in d if not isinstance(d, OrientBinaryObject)]))
        elif isinstance(d, OrientRecordLink):
            return d.get_hash()
        elif isinstance(d, OrientBinaryObject):

            # This should never be reached:
            return None
        else:
            return d

    out = {}
    out['class'] = r._class
    out['rid'] = r._rid
    out['version'] = r._version
    if r.oRecordData:
        storage = rec(r.oRecordData)
    else:
        storage = {}
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

    def to_str(obj):
        if isinstance(obj, OrientBinaryObject):
            s = '<OrientBinaryObject @ %s>' % hex(obj.__hash__())
        elif isinstance(obj, OrientRecordLink):
            s = '%s' % obj.get_hash()
        else:
            s = str(obj)
        return s

    # Find keys in record; look inside r['storage'] because it may contain more keys:
    # XXX this approach might post problems if a record contains a property
    # called 'class', 'storage', or 'rid':
    cols = set()
    for r in results:
        keys = r.keys()
        if 'storage' in keys:
            keys.remove('storage')
            keys.extend(r['storage'].keys())
        cols.update(keys)

    # Don't print the version:
    try:
        cols.remove('version')
    except:
        pass

    # Add header for row number column:
    cols_list = ['#']

    # Rearrange columns to print RID and class first:
    if 'rid' in cols:
        cols_list.append('rid')
        cols.remove('rid')
    if 'class' in cols:
        cols_list.append('class')
        cols.remove('class')
    cols_list.extend(cols)
    cols = cols_list

    p = prettytable.PrettyTable(cols)
    for i, r in enumerate(results):
        row = []
        for k in cols:
            if r.has_key(k):
                s = to_str(r[k])
            elif r['storage'].has_key(k):
                s = to_str(r['storage'][k])
            elif k == '#':
                s = str(i)
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
    opts, cell = self.parse_options(cell, 'gjt:', posix=False)

    server = 'localhost'
    db_name = ''
    port = 2424
    user = ''
    passwd = ''
    cmd = ''
    cmd_type = 'cmd'
    display = ()

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

                # user[:password]@server[:port][/db_name]
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

    if opts.has_key('j'):
        display = ('json',)
    elif opts.has_key('t'):
        try:
            max_len = int(opts['t'])
        except:
            raise ValueError('integer expected')
        else:
            display = ('table', max_len)
    if opts.has_key('g'):
        cmd_type = 'gremlin'
    elif re.search('^select .*', cmd):
        cmd_type = 'query'
    else:
        cmd_type = 'cmd'

    return {'server': server, 'db_name': db_name, 'port': port,
            'user': user, 'passwd': passwd, 'cmd': cmd, 
            'cmd_type': cmd_type, 'display': display}

@magics_class
class OrientMagic(Magics, Configurable):

    # Maintain two separate dicts of connections so that client-specific
    # commands can be executed independently of database-specific commands:
    clients = {} # client connections; keys are "user@db_name"    
    db = {}      # connections to specific databases; keys are "user@db_name"

    last_client_key = ''
    last_db_key = ''

    @line_magic
    @cell_magic
    def orient(self, line, cell=''):
        """
        Runs an OrientDB query against an OrientDB database.

        Multiple database connections are supported. Once a connection has been
        established, it can be used by specifying its user@server/dbname. A
        separate database-independent connection to the server is maintained to
        permit server-specific commands without having to subsequently reconnect
        to the currently open database. If no connect string is specified after
        at least one connection has been established, the most recently used
        connection will be used to execute the query.

        Queries are assumed to be in OrientDB SQL. Gremlin queries may be run by
        specifying the '-g' option. Several special commands similar to those
        provided by the OrientDB console (such as 'list databases',
        'list classes', etc.) are also recognized.

        Query results are returned as a list of dictionaries. Specifying the
        options '-j' or '-t N' (where 'N' is an integer) will respectively print
        the results in JSON or tabular format (with a maximum field width of 'N'
        characters) rather than returning them.

        Examples
        --------
        %orient user:passwd@server/dbname

        %orient user:passwd@server:2424/dbname

        %orient disconnect

        %%orient user@server/dbname
        select from v

        %orient -g user@server/dbname g.V.has('name', 'foo')

        %orient current server

        %orient current database

        %orient list classes

        %orient list databases

        %%orient user@server
        list databases

        %orient create database foobar memory graph

        %orient drop database foobar

        persons = %orient select * from persons

        %orient -t 100 select * from persons

        See Also
        --------
        %oview - View results of OrientDB query.
        """

        parsed = parse('%s\n%s' % (line, cell), self)

        # Update last user + server:
        if parsed['user'] and parsed['server']:
            client_key = parsed['user']+'@'+parsed['server']
            self.last_client_key = client_key
        else:
            client_key = self.last_client_key

        # Update last server and db:
        if parsed['user'] and parsed['server'] and parsed['db_name']:
            db_key = parsed['user']+'@'+parsed['server'] + '/' + parsed['db_name']
            self.last_db_key = db_key
        else:
            db_key = self.last_db_key

        if client_key in self.clients:
            client = self.clients[client_key]
        elif client_key:
            client = pyorient.OrientDB(parsed['server'], parsed['port'])
            client.connect(parsed['user'], parsed['passwd'])
            self.clients[client_key] = client
        else:
            client = None

        # If no database name is specified, don't try to connect to any database:
        if db_key in self.db:
            db_client = self.db[db_key]
        elif db_key:
            db_client = pyorient.OrientDB(parsed['server'], parsed['port'])
            db_client.connect(parsed['user'], parsed['passwd'])
            db_client.db_open(parsed['db_name'], parsed['user'], parsed['passwd'])
            self.db[db_key] = db_client
        else:
            db_client = None

        results = None
        if parsed['cmd']:
            if parsed['cmd'] == 'current server':
                results = client_key
            elif parsed['cmd'] == 'current database':
                results = db_key
            elif parsed['cmd'] == 'disconnect':
                del self.db[db_key]
                self.last_db_key = ''
            elif parsed['cmd'] == 'list databases':
                if client is None:
                    raise RuntimeError('no server accessed')
                r = client.db_list()
                if r:
                    results = r.oRecordData['databases']
                else:
                    results = {}
            elif parsed['cmd'] == 'list classes':
                if db_client is None:
                    raise RuntimeError('no database opened')
                results = db_client.query('select name from '
                                          '(select expand(classes) from metadata:schema)')
                results = [r.oRecordData['name'] for r in results]
            elif parsed['cmd'].startswith('drop database'):
                if client is None:
                    raise RuntimeError('no server accessed')
                tokens = re.sub('drop database', '',
                                parsed['cmd']).strip().split()
                if len(tokens) < 1:
                    raise ValueError('database name not specified')
                else:
                    name = tokens.pop(0)
                    client.db_drop(name)
            elif parsed['cmd'].startswith('create database'):
                if client is None:
                    raise RuntimeError('no server accessed')
                tokens = re.sub('create database', '',
                                parsed['cmd']).strip().split()
                if len(tokens) < 1:
                    raise ValueError('database name not specified')
                else:
                    name = tokens.pop(0)
                    storage = 'plocal'
                    db_type = 'graph'
                    if len(tokens) > 0:
                        storage = tokens[0]
                    if len(tokens) > 1:
                        db_type = tokens[1]
                    client.db_create(name, db_type, storage)
            elif parsed['cmd_type'] == 'gremlin':
                if db_client is None:
                    raise RuntimeError('no database opened')

                # Try wrapping Gremlin queries in a pipeline and/or closure to
                # convert the results to ODocument instances (if possible) so as
                # to prevent serialization failure; see http://bit.ly/1hhm06F
                cmd = """
def make_doc = {x -> new com.orientechnologies.orient.core.record.impl.ODocument(x)};
p = { -> %s}; result = p();
try {make_doc(result)}
catch (all) {
if (result instanceof GremlinGroovyPipeline){
    result.transform{try {make_doc(it)} catch (a0) {it}}}
else if (result instanceof Iterable) {
    try {(new GremlinGroovyPipeline()).start(result)}
    catch (a1) {result}}
else {
     try {(new GremlinGroovyPipeline()).start(result).transform{try {make_doc(it)} catch (a2) {it}}}
     catch (a3) {result}}}
""" % parsed['cmd']
                results = db_client.gremlin(cmd)
                results = [orientrecord_to_dict(r) if isinstance(r,
                           pyorient.otypes.OrientRecord) else r for r in results]
            elif parsed['cmd_type'] == 'query':
                if db_client is None:
                    raise RuntimeError('no database opened')

                results = db_client.query(parsed['cmd'])
                results = [orientrecord_to_dict(r) if isinstance(r,
                           pyorient.otypes.OrientRecord) else r for r in results]
            else:
                if db_client is None:
                    raise RuntimeError('no database opened')

                db_client.command(parsed['cmd'])
        if parsed['display'] and results is not None:
            if parsed['display'][0] == 'json':
                show_json(results)
            elif parsed['display'][0] == 'table':
                show_table(results, parsed['display'][1])
        else:
            return results

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

        # Cleanly shut down all connections:
        for db_client in self.db:
            db_client.db_close()
        for client in self.clients:
            client.shutdown()

def load_ipython_extension(ip):
    ip.register_magics(OrientMagic)
