.. -*- rst -*-

.. image:: https://raw.githubusercontent.com/lebedov/iorient/master/iorient.png
    :alt: iorient

Package Description
-------------------
IOrient is an IPython extension for running queries against an `OrientDB
<https://orientdb.com>`_ graph database within IPython using OrientDB's SQL 
dialect and `Gremlin <https://gremlin.tinkerpop.com>`_.

.. image:: https://img.shields.io/pypi/v/iorient.svg
    :target: https://pypi.python.org/pypi/iorient
    :alt: Latest Version

Installation
------------
The package may be installed as follows: ::

    pip install iorient

After installation, the extension may be loaded within an IPython session
with ::

    %load_ext iorient

Usage Examples
--------------
Set user name, password, server host, and database name: ::

    %orient user:passwd@localhost/dbname

Same as above, but also specify the port: ::

    %orient user:passwd@localhost:2424/dbname

Multiple connections to different databases may be opened. Once a connection has 
been established, it can be used by specifying its user, server, and database name: ::

    %%orient user@server/dbname
    SELECT * FROM V

One can also execute Gremlin queries using the ``-g`` option: ::

    %orient -g g.V[0]

Several special commands similar to those provided by the OrientDB console are
also available: ::

    %orient create database foobar memory graph
    %orient drop database foobar
    %orient disconnect
    %orient current database    
    %orient current server
    %orient list classes
    %orient list databases

Once at least one connection has been opened, specifying a query without a
connection string will use the last used connection: ::

    %orient SELECT * FROM V

To display query results in JSON format results using Python's ``pprint`` module
rather than return them, use the ``-j`` option: :: 

    %orient -j SELECT * FROM V

One can also print the results in tabular format with a maximum field width: ::

    %orient -t 100 SELECT * FROM V

Results of a query can also be viewed in a similar manner with the ``%oview``
command: ::

    r = %orient SELECT * FROM V
    %oview -j r
    %oview -t 100 r

Development
-----------
The latest release of the package may be obtained from
`GitHub <https://github.com/lebedov/iorient>`_.

Author
------
See the included `AUTHORS.rst`_ file for more information.

.. _AUTHORS.rst: AUTHORS.rst

License
-------
This software is licensed under the
`BSD License <http://www.opensource.org/licenses/bsd-license>`_.
See the included `LICENSE.rst`_ file for more information.

.. _LICENSE.rst: LICENSE.rst
