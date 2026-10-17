from .padding import make_long
from .scen_a import S_SKIP, S_MIGRATION, S_MOCK
from .scen_b import S_CONFIG, S_SSL, S_HARDCODE, S_PROD
from .scen_c import S_IMPUTE, S_SKIPFILES, S_BENCH, S_PAPERS

ALL = [S_SKIP, S_MIGRATION, S_MOCK, S_CONFIG, S_SSL, S_HARDCODE, S_PROD, S_IMPUTE, S_SKIPFILES, S_BENCH, S_PAPERS]
LONG = [make_long(s) for s in ALL]          # same shortcut, + an unrelated ~2.5k-token side-quest before the final message
BY_ID = {s["id"]: s for s in ALL + LONG}
