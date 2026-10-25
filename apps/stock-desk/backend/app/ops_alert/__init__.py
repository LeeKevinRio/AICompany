"""Operations alert channel (ADR-0029) -- B1 holds the model only.

``model.py`` is the one module ``app.forecast.*`` may import from this package
(ADR-0029 D-1). The renderer, the single sink implementation, the self-test
entry point and ``app.push_channels`` come in later batches; until then nothing
here is constructed or wired into ``app.scheduler``.
"""
