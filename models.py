from typing import Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field




# =========================
# 1. Regions
# =========================

class Region(SQLModel, table=True):
    __tablename__ = "Regions"

    region_id: Optional[int] = Field(default=None, primary_key=True)
    name_th: str = Field(index=True, unique=True)
    total_population: int = Field(default=20)


# =========================
# 2. Constituencies
# =========================

class Constituency(SQLModel, table=True):
    __tablename__ = "Constituencies"

    const_id: Optional[int] = Field(default=None, primary_key=True)
    region_id: int = Field(foreign_key="Regions.region_id")
    const_number: int
    total_eligible_voters: int = Field(default=0)


# =========================
# 3. Parties
# =========================

class Party(SQLModel, table=True):
    __tablename__ = "Parties"

    party_id: Optional[int] = Field(default=None, primary_key=True)
    party_name: str = Field(unique=True, index=True)
    party_leader: Optional[str] = None
    party_logo_url: Optional[str] = None


# =========================
# 4. Candidates
# =========================

class Candidate(SQLModel, table=True):
    __tablename__ = "Candidates"

    candidate_id: Optional[int] = Field(default=None, primary_key=True)
    const_id: int = Field(foreign_key="Constituencies.const_id")
    party_id: int = Field(foreign_key="Parties.party_id")
    candidate_number: int
    full_name: str


# =========================
# 5. Voters
# =========================

class Voter(SQLModel, table=True):
    __tablename__ = "Voters"

    voter_id: Optional[int] = Field(default=None, primary_key=True)
    citizen_id: str = Field(unique=True, index=True)
    full_name: str
    const_id: int = Field(foreign_key="Constituencies.const_id")

    has_voted_const: int = Field(default=0)  # 0 = ยังไม่เลือก
    has_voted_list: int = Field(default=0)   # 0 = ยังไม่เลือก


# =========================
# 6. Ballots (Anonymous Votes)
# =========================

class Ballot(SQLModel, table=True):
    __tablename__ = "Ballots"

    ballot_id: Optional[int] = Field(default=None, primary_key=True)

    voter_id: int = Field(foreign_key="Voters.voter_id")  # เพิ่ม
    const_id: int = Field(foreign_key="Constituencies.const_id")

    candidate_id: Optional[int] = Field(
        default=None,
        foreign_key="Candidates.candidate_id"
    )
    party_id: Optional[int] = Field(
        default=None,
        foreign_key="Parties.party_id"
    )

    vote_type: str
    is_valid: bool = Field(default=True)
    voted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))