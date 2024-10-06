from dataclasses import dataclass
import datetime


@dataclass
class NonOmniscientDatedelta:
    years: int | None = None
    days: int | None = None

    def __str__(self):
        # this assumes this is in reference to "today" (whatever that is)
        if self.years is None:
            y_part = "some year"
        elif self.years > 0:
            if self.years == 1:
                y_part = "last year"
            else:
                y_part = f"{self.years} years ago"
        elif self.years < 0:
            if self.years == -1:
                y_part = "next year"
            else:
                y_part = f"in {abs(self.years)} years"
        else:
            y_part = "this year"

        if self.days is None:
            d_part = "some day"
        elif self.days > 0:
            if self.days == 1:
                d_part = "yesterday"
            else:
                d_part = f"{self.days} days ago"
        elif self.days < 0:
            if self.days == -1:
                d_part = "tomorrow"
            else:
                d_part = f"in {abs(self.days)} days"
        else:
            d_part = "today"

        if self.years is None and self.days is None:
            return "some day"
        elif self.years and self.years > 0 and self.days and self.days < 0:
            return f"{d_part}, {y_part}"
        elif self.years and self.years < 0 and self.days == 0:
            if self.years == -1:
                return "1 year from today"
            else:
                return f"{abs(self.years)} years from today"
        elif self.days is None:
            return f"{d_part} {y_part}"
        elif self.days and self.years and self.days > 0 and self.years > 0 and 1 not in (self.days, self.years):
            return f"{self.years} years and {self.days} days ago"
        elif self.days and self.years and self.days < 0 and self.years < 0 and -1 not in (self.days, self.years):
            return f"in {abs(self.years)} years and {abs(self.days)} days"
        elif self.years != 0:
            return f"{y_part}, {d_part}"
        else:
            return d_part



def subtract_years_and_days(dt1, dt2):
    years = dt1.year - dt2.year

    dt1_in_dt2_year = dt1.replace(year=dt2.year)
    if dt1_in_dt2_year > dt2:
        days = (dt1_in_dt2_year - dt2).days
    else:
        days = -(dt2 - dt1_in_dt2_year).days
    return years, days


class NonOmniscientDate:
    def __init__(self, representation):
        self.year, self.month, self.day = representation.split("-")
        self.is_omniscient = "?" not in representation

    def __rsub__(self, other):
        assert isinstance(other, datetime.date)
        if self.is_omniscient:
            d = datetime.date(
                int(self.year),
                int(self.month),
                int(self.day),
            )
            years, days = subtract_years_and_days(other, d)
            return NonOmniscientDatedelta(
                years=years,
                days=days,
            )
        elif self.month.isdecimal() and self.day.isdecimal():
            # 19??-04-17
            return NonOmniscientDatedelta(
                days=(
                    other.replace(year=2000)
                    - datetime.date(2000, int(self.month), int(self.day))
                ).days,
            )
        elif self.year.isdecimal():
            return NonOmniscientDatedelta(
                years=other.year - int(self.year),
            )
        else:
            return NonOmniscientDatedelta()
