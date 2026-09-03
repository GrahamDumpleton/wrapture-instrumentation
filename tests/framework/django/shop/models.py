"""The one model the suite queries."""

from __future__ import annotations

from django.db import models


class Item(models.Model):
    """A stocked item: the table the ORM tests query and populate."""

    name = models.CharField(max_length=50)
    price = models.IntegerField(default=0)
