import datetime
from dataclasses import dataclass, asdict
from typing import List
from src.project.goal import Goal
from session import Session


@dataclass
class Project:
    title: str
    photo_url: str
    goals: List[Goal]
    due_date: datetime.date
    sessions: List[session]

    def add_session(self, session: Session):
        self.sessions.append(session)

    def remove_session(self, session: Session):
        self.sessions.remove(session)

    def list_sessions():
        return sessions

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
        data["sessions"] = [session.to_dict() for session in self.sessions]
        return data
