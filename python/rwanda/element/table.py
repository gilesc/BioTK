import io
import uuid
import pickle

import numpy as np
import pandas as pd
from bottle import request

from .. import env

class RAMCache(object):
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data[key]

    def set(self, key, value):
        self.data[key] = value

cache = RAMCache()

class Table(Element):
    """
    Tabular data to be rendered to HTML. This can either be a transient
    table, or a table that will be cached for later AJAX calls.
    """
    TEMPLATE = env.get_template("table")

    def __init__(self, data, 
            title=None, link_format=None, link_columns=None,
            classes=None, server_side=False):
        self.data = data
        self.title = title
        self.link_format = link_format
        self.link_columns = link_columns
        self.classes = [] if classes is None else classes
        self.server_side = server_side

        if self.server_side:
            self.classes.append("data-table")
            self.uuid = str(uuid.uuid4())
            cache.set(self.uuid, pickle.dumps(self))

    @staticmethod
    def load(uuid):
        return pickle.loads(cache.get(uuid))

    def _render(self):
        return self.TEMPLATE.render(table=self)

    def ajax(self, params):
        # FIXME: implement filtering, sorting
        start = int(params["start"])
        length = int(params["length"])
        order_column = int(params["order[0][column]"])
        order_ascending = params["order[0][dir]"] == "asc"
        search = params["search[value]"]

        def scalar(x):
            if isinstance(x, str):
                return x
            else:
                x = np.asscalar(x)
            if isinstance(x, float):
                return round(x, 2)
            return x

        if search:
            ix = np.zeros(self.data.shape[0], dtype=bool)
            for j in range(self.data.shape[1]):
                if self.data.dtypes[j] == object:
                    ix = np.logical_or(ix,
                            np.array(self.data.iloc[:,j]\
                                    .str.lower()\
                                    .str.contains(search.lower(), 
                                        regex=False),
                                    dtype=bool))
        else:
            ix = np.ones(self.data.shape[0], dtype=bool)
            
        if ix.sum() > 0:
            length = min(length, ix.sum()-start)
            rows = list(map(lambda row: tuple(map(scalar, row)), 
                self.data[ix]\
                        .sort(self.data.columns[order_column], 
                            ascending=order_ascending)\
                                    .iloc[start:(start+length),:]\
                                    .to_records(index=False)))
        else:
            rows = []

        o = {
            "draw": int(params["draw"]),
            "recordsTotal": self.data.shape[0],
            "recordsFiltered": int(ix.sum()),
            "data": rows
        }
        return o

def sql_to_table(q, *args, **kwargs):
    c = db.cursor()
    c.execute(q, tuple(args))
    columns = [d[0] for d in c.description]
    rows = []
    for row in c:
        row = [item if item is not None else "-"
               for item in row]
        rows.append(row)
    df = pd.DataFrame(rows, columns=columns)
    return Table(df, server_side=True, **kwargs)

def view_to_table(view, limit=None, **kwargs):
    q = "SELECT * FROM %s" % view
    if limit:
        q += " LIMIT %s" % limit
    return sql_to_table(q, **kwargs)

def fn_to_table(fn_name, *args, **kwargs):
    quoted_args = ["'"+a+"'" if isinstance(a,str) else a
            for a in args]
    return sql_to_table("SELECT * FROM %s(%s)" % \
            (fn_name, ", ".join(quoted_args)),
            **kwargs)

@root.post("/api/table/<uuid>")
def fn(uuid):
    params = dict(request.params.decode())
    table = Table.load(uuid)
    return table.ajax(params)

@root.get("/api/table/<uuid>/csv")
def fn(uuid):
    buffer = io.StringIO()
    Table.load(uuid)\
            .data\
            .to_csv(buffer, float_format="%0.3f")
    response.content_type = "application/csv"
    response.set_header("Content-Disposition", 
            "attachment; filename=age_atlas.csv")
    return buffer.getvalue()
