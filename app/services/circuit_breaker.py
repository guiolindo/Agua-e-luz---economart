"""Disjuntor em processo para dependências externas (Gemini).

Sem ele, uma queda do Google faz cada envio de conta esperar o timeout inteiro (e as retentativas) antes de falhar.
Após `failure_threshold` falhas seguidas o disjuntor abre e rejeita na hora por `reset_seconds`; depois deixa passar
uma chamada de teste (meio-aberto): sucesso fecha, falha reabre. Estado por processo (basta para 1 instância).
"""
import threading
import time
from contextlib import contextmanager


class BreakerOpen(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, reset_seconds: float = 30.0, clock=time.monotonic):
        self.name, self.failure_threshold, self.reset_seconds, self._clock = name, failure_threshold, reset_seconds, clock
        self._failures, self._opened_at, self._probing = 0, None, False
        self._lock = threading.Lock()

    def _allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if self._clock() - self._opened_at >= self.reset_seconds and not self._probing:
                self._probing = True            # só uma chamada de teste por vez
                return True
            return False

    def reset(self) -> None:
        with self._lock:
            self._failures, self._opened_at, self._probing = 0, None, False

    @contextmanager
    def call(self, counts=lambda exc: True):
        """`counts(exc)` decide se a exceção é falha da dependência (conta) ou erro do chamador (não conta)."""
        if not self._allow():
            raise BreakerOpen(self.name)
        try:
            yield
        except Exception as exc:
            with self._lock:
                self._probing = False
                if counts(exc):
                    self._failures += 1
                    if self._failures >= self.failure_threshold or self._opened_at is not None:
                        self._opened_at = self._clock()
            raise
        else:
            self.reset()


gemini_breaker = CircuitBreaker("gemini")
