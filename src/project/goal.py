import datetime
from dataclasses import dataclass, asdict


@dataclass
class Goal:
    name: str
    due_date: datetime.date
    status: bool = False

    def mark_as_done(self):
        self.status = True

    def mark_as_undone(self):
        self.status = False

    def __str__(self):
        return f"Goal: {self.name}, Due: {self.due_date}, Status: {'Done' if self.status else 'Pending'}"

    def to_dict(self):
        data = asdict(self)
        data["due_date"] = data["due_date"].isoformat()
        return data

