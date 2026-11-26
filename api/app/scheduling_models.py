from datetime import date, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CourseInput(Input):
    title: str = Field(min_length=1, max_length=200)
    teacher_id: int | None = Field(default=None, gt=0)

    @field_validator('title')
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError('課程名稱不得空白')
        return value.strip()


class TimeInput(Input):
    room_id: int = Field(gt=0)
    start_time: time
    end_time: time

    @model_validator(mode='after')
    def valid_times(self):
        if self.start_time.tzinfo or self.end_time.tzinfo:
            raise ValueError('請使用臺灣本地時間，不附時區')
        if self.start_time >= self.end_time:
            raise ValueError('結束時間必須晚於開始時間，不支援跨午夜')
        return self


class SlotInput(TimeInput):
    start_date: date
    end_date: date
    weekday: int = Field(ge=0, le=6, description='星期一=0，星期日=6')

    @model_validator(mode='after')
    def valid_dates(self):
        if not 0 <= (self.end_date - self.start_date).days <= 366:
            raise ValueError('起訖順序不正確或超過 366 天')
        offset = (self.weekday - self.start_date.weekday()) % 7
        if offset > (self.end_date-self.start_date).days:
            raise ValueError('此區間沒有指定星期的上課日')
        return self


class ChangeInput(TimeInput):
    scope: Literal['single', 'future']
    effective_date: date = Field(description='原週課表中受影響的上課日期')
    new_date: date = Field(description='single：新日期；future：新系列第一個上課日期')
    new_weekday: int = Field(ge=0, le=6)
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def valid_day(self):
        if self.new_date.weekday() != self.new_weekday:
            raise ValueError('new_date 與 new_weekday 不一致')
        return self


class ReviewInput(Input):
    status: Literal['approved', 'rejected']
    note: str = Field(default='', max_length=2000)
