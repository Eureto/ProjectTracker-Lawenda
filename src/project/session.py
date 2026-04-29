
import datetime
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class Session:
    title: str
    start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    end_time: Optional[datetime.datetime] = field(default=None)
    duration: Optional[datetime.timedelta] = field(default=None)

    def stop_session(self):
        self.end_time = datetime.datetime.now()
        self.duration = self.end_time - self.start_time

    def __str__(self):
        return f"Session: {self.title}, Start: {self.start_time}, End: {self.end_time}, Duration: {self.duration}"

    def to_dict(self):
        data = asdict(self)
        if data["start_time"]:
            data["start_time"] = data["start_time"].isoformat()
        if data["end_time"]:
            data["end_time"] = data["end_time"].isoformat()
        if data["duration"]:
            data["duration"] = data["duration"].total_seconds()
        return data
