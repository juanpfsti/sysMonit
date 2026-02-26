# hooks/hook-pandas.py
# PyInstaller hook explícito para pandas.
# Garante coleta dos .pyd compilados em pandas._libs (tslibs, etc.)
# mesmo quando --collect-all pandas falha por conflito de ambiente.

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all("pandas")

# Submodulos críticos com extensões Cython (.pyd) que o hook padrão pode perder
hiddenimports += collect_submodules("pandas._libs")
hiddenimports += collect_submodules("pandas.core")
hiddenimports += collect_submodules("pandas.io")
hiddenimports += collect_submodules("pandas.compat")
hiddenimports += [
    "pandas._libs.tslibs.np_datetime",
    "pandas._libs.tslibs.nattype",
    "pandas._libs.tslibs.timedeltas",
    "pandas._libs.tslibs.timestamps",
    "pandas._libs.tslibs.offsets",
    "pandas._libs.tslibs.period",
    "pandas._libs.tslibs.parsing",
    "pandas._libs.tslibs.timezones",
    "pandas._libs.tslibs.conversion",
    "pandas._libs.tslibs.fields",
    "pandas._libs.tslibs.vectorized",
    "pandas._libs.lib",
    "pandas._libs.hashtable",
    "pandas._libs.index",
    "pandas._libs.internals",
    "pandas._libs.join",
    "pandas._libs.missing",
    "pandas._libs.ops",
    "pandas._libs.ops_dispatch",
    "pandas._libs.parsers",
    "pandas._libs.reduction",
    "pandas._libs.reshape",
    "pandas._libs.sparse",
    "pandas._libs.writers",
    "pandas._libs.window.aggregations",
    "pandas._libs.window.indexers",
]
