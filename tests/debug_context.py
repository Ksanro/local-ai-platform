"""Debug script for context builder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.context.builder import ContextBuilder
from packages.context.models import ContextQuery
from packages.repository.index.models import Module, RepositoryIndex, RepositoryStatistics, Symbol, SymbolType

symbols = [
    Symbol(id='main.App', name='App', qualified_name='main.App', symbol_type=SymbolType.CLASS, module='main.py', lineno=1),
    Symbol(id='main.App.run', name='run', qualified_name='main.App.run', symbol_type=SymbolType.METHOD, module='main.py', lineno=5),
]
modules = {'main.py': Module(path='main.py', symbols=symbols)}
idx = RepositoryIndex(
    modules=modules,
    _symbols=symbols,
    _relationships=[],
    _statistics=RepositoryStatistics(module_count=1, class_count=1, function_count=0, method_count=1, symbol_count=2),
)
print('Index symbols:', len(list(idx.symbols())))
builder = ContextBuilder(idx)
result = builder.build(ContextQuery(text='test query', max_symbols=20, max_modules=10))
print('Candidates:', len(result.candidates))
for c in result.candidates:
    print(f'  {c.qualified_name}: score={c.score} reasons={c.reasons}')