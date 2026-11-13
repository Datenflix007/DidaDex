"""Backward-compatible desktop entry point for the unified launcher."""
from __future__ import annotations

from engine import DidaDexDesktop

__all__ = ('DidaDexDesktop',)


if __name__ == '__main__':
    DidaDexDesktop().mainloop()
