"""Fascia notturna: intervallo di lettura più lungo in un orario scelto.

Ogni lettura risveglia il glo; sotto carica il glo vibra a ogni risveglio,
quindi di notte conviene interrogarlo di rado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta


def parse_time(value: str) -> time:
    """'HH:MM' o 'HH:MM:SS' → time. ValueError se il formato non è valido."""
    return time.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class NightWindow:
    """Fascia oraria [start, end) che può scavalcare la mezzanotte."""

    start: time
    end: time
    interval: timedelta

    @property
    def enabled(self) -> bool:
        """Disattivata se l'intervallo è 0 o la fascia è vuota."""
        return self.interval > timedelta(0) and self.start != self.end

    def contains(self, moment: time) -> bool:
        """True se l'orario cade nella fascia."""
        if not self.enabled:
            return False
        if self.start < self.end:
            return self.start <= moment < self.end
        return moment >= self.start or moment < self.end  # scavalca la mezzanotte

    def until_end(self, now: datetime) -> timedelta:
        """Tempo che manca alla fine della fascia (now deve esserci dentro)."""
        end: datetime = now.replace(
            hour=self.end.hour, minute=self.end.minute, second=self.end.second, microsecond=0
        )
        if end <= now:
            end += timedelta(days=1)
        return end - now

    def interval_at(self, now: datetime, normal: timedelta) -> timedelta:
        """Intervallo da usare adesso.

        Nella fascia si usa quello notturno, ma senza superare la fine della
        fascia (così al mattino le letture riprendono puntuali) e mai sotto
        l'intervallo normale.
        """
        if not self.contains(now.time()):
            return normal
        return max(normal, min(self.interval, self.until_end(now)))
