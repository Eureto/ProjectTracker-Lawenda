import datetime
from dataclasses import dataclass, asdict
from typing import List
from src.project.goal import Goal


@dataclass
class Project:
    title: str
    photo_url: str
    goals: List[Goal]
    due_date: datetime.date

    def add_goal(self, goal: Goal):
        self.goals.append(goal)

    def remove_goal(self, goal: Goal):
        self.goals.remove(goal)
    
    def get_goals(self):
        return self.goals

    def to_dict(self):
        data = asdict(self)
        data["due_date"] = self.due_date.isoformat()
        data["goals"] = [goal.to_dict() for goal in self.goals]
        return data
