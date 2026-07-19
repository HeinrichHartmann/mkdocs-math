---
outline_enabled: false
id: E0002
title: First Result
kind: proposition
status: established
notation: E0001
depends_on: [E0001]
validation:
  numeric:
    file: validation/python/E0002_test.py
  symbolic:
    file: validation/sympy/E0002_test.py
published_at: [TestKey2026]
---

# E0002 — First Result

**Proposition.** Using the notation from E0001, for all $x \in X$ we have $x \in X$.

**Proof.** Immediate from the definition in E0001. $\blacksquare$
