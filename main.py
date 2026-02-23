from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select, func
from sqlalchemy.orm import aliased
from typing import List

from database import create_db_and_tables, get_session
from models import Region, Constituency, Party, Candidate, Voter, Ballot

app = FastAPI(title="Election Backend Midterm")


# =========================
# Startup
# =========================
@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# =========================================================
# Regions
# =========================================================
@app.post("/regions")
def create_region(region: Region, session: Session = Depends(get_session)):
    session.add(region)
    session.commit()
    session.refresh(region)
    return region


@app.get("/regions", response_model=List[Region])
def get_regions(session: Session = Depends(get_session)):
    return session.exec(select(Region)).all()


# =========================================================
# Constituencies
# =========================================================
@app.post("/constituencies")
def create_constituency(constituency: Constituency, session: Session = Depends(get_session)):
    # optional: เช็ค region มีจริง
    region = session.get(Region, constituency.region_id)
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    session.add(constituency)
    session.commit()
    session.refresh(constituency)
    return constituency


@app.get("/constituencies", response_model=List[Constituency])
def get_constituencies(session: Session = Depends(get_session)):
    return session.exec(select(Constituency)).all()


# =========================================================
# Parties
# =========================================================
@app.post("/parties")
def create_party(party: Party, session: Session = Depends(get_session)):
    session.add(party)
    session.commit()
    session.refresh(party)
    return party


@app.get("/parties", response_model=List[Party])
def get_parties(session: Session = Depends(get_session)):
    return session.exec(select(Party)).all()


# =========================================================
# Candidates
# =========================================================
@app.post("/candidates")
def create_candidate(candidate: Candidate, session: Session = Depends(get_session)):
    # optional: เช็ค const + party มีจริง
    const = session.get(Constituency, candidate.const_id)
    if not const:
        raise HTTPException(status_code=404, detail="Constituency not found")

    party = session.get(Party, candidate.party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")

    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


@app.get("/candidates", response_model=List[Candidate])
def get_candidates(session: Session = Depends(get_session)):
    return session.exec(select(Candidate)).all()


# =========================================================
# Voters
# =========================================================
@app.post("/voters")
def create_voter(voter: Voter, session: Session = Depends(get_session)):
    const = session.get(Constituency, voter.const_id)
    if not const:
        raise HTTPException(status_code=404, detail="Constituency not found")

    session.add(voter)
    session.commit()
    session.refresh(voter)
    return voter


@app.get("/voters", response_model=List[Voter])
def get_voters(session: Session = Depends(get_session)):
    return session.exec(select(Voter)).all()


@app.put("/voters/{voter_id}/status")
def update_voter_status(
    voter_id: int,
    has_voted_const: int | None = None,
    has_voted_list: int | None = None,
    session: Session = Depends(get_session),
):
    voter = session.get(Voter, voter_id)
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    if has_voted_const is not None:
        voter.has_voted_const = has_voted_const
    if has_voted_list is not None:
        voter.has_voted_list = has_voted_list

    session.add(voter)
    session.commit()
    session.refresh(voter)
    return voter


# =========================================================
# Ballots (สำคัญ)
# =========================================================
@app.post("/ballots")
def create_ballot(ballot: Ballot, session: Session = Depends(get_session)):
    """
    Validation ครบ:
    - voter ต้องมีจริง
    - voter ต้องอยู่เขตเดียวกับ ballot.const_id
    - vote_type ถูกต้อง
    - Constituency: ต้องมี candidate_id, ห้ามส่ง party_id, candidate ต้องอยู่เขตเดียวกัน
    - PartyList: ต้องมี party_id, ห้ามส่ง candidate_id
    - กันโหวตซ้ำ + update has_voted_* อัตโนมัติ
    """

    voter = session.get(Voter, ballot.voter_id)
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    # voter ต้องโหวตในเขตตัวเองเท่านั้น (เพื่อสมจริง)
    if voter.const_id != ballot.const_id:
        raise HTTPException(status_code=400, detail="Voter not in this constituency")

    if ballot.vote_type not in ["Constituency", "PartyList"]:
        raise HTTPException(status_code=400, detail="Invalid vote_type")

    if ballot.vote_type == "Constituency":
        if ballot.candidate_id is None:
            raise HTTPException(status_code=400, detail="candidate_id required")
        if ballot.party_id is not None:
            raise HTTPException(status_code=400, detail="Do not send party_id for constituency vote")
        if voter.has_voted_const:
            raise HTTPException(status_code=400, detail="Already voted constituency")

        candidate = session.get(Candidate, ballot.candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        if candidate.const_id != ballot.const_id:
            raise HTTPException(status_code=400, detail="Candidate not in this constituency")

        voter.has_voted_const = 1

    elif ballot.vote_type == "PartyList":
        if ballot.party_id is None:
            raise HTTPException(status_code=400, detail="party_id required")
        if ballot.candidate_id is not None:
            raise HTTPException(status_code=400, detail="Do not send candidate_id for party vote")
        if voter.has_voted_list:
            raise HTTPException(status_code=400, detail="Already voted party list")

        party = session.get(Party, ballot.party_id)
        if not party:
            raise HTTPException(status_code=404, detail="Party not found")

        voter.has_voted_list = 1

    session.add(ballot)
    session.add(voter)
    session.commit()
    session.refresh(ballot)
    return ballot


# ----- Ballots list: โชว์ชื่อไทยทั้งหมด -----

@app.get("/ballots")
def get_ballots_final(session: Session = Depends(get_session)):
    PartyBallot = aliased(Party)
    PartyCandidate = aliased(Party)

    status_expr = (
        ((Ballot.vote_type == "Constituency") & (Ballot.candidate_id.is_not(None)) & (Ballot.party_id.is_(None))) |
        ((Ballot.vote_type == "PartyList") & (Ballot.party_id.is_not(None)) & (Ballot.candidate_id.is_(None)))
    )

    statement = (
        select(
            Ballot.ballot_id,
            Ballot.vote_type,
            Ballot.voted_at,
            status_expr.label("status"),
            Candidate.full_name.label("candidate_name"),
            func.coalesce(
                PartyBallot.party_name,      # PartyList
                PartyCandidate.party_name    # Constituency ผ่าน Candidate.party_id
            ).label("party_name"),
        )
        .select_from(Ballot)
        .outerjoin(Candidate, Candidate.candidate_id == Ballot.candidate_id)
        .outerjoin(PartyBallot, PartyBallot.party_id == Ballot.party_id)
        .outerjoin(PartyCandidate, PartyCandidate.party_id == Candidate.party_id)
        .order_by(Ballot.ballot_id)
    )

    rows = session.exec(statement).all()
    out = []

    for r in rows:
        d = r._asdict()

        item = {
            "ballot_id": d["ballot_id"],
            "voted_at": d["voted_at"],
            "ballot_note": "บัตรดี" if d["status"] else "บัตรเสีย",
            "vote_type": d["vote_type"],
        }

        # ใส่ key ตามประเภทเท่านั้น
        if d["status"]:
            if d["vote_type"] == "Constituency":
                item["candidate_name"] = d["candidate_name"]
            elif d["vote_type"] == "PartyList":
                item["party_name"] = d["party_name"]

        out.append(item)

    return out
@app.get("/ballots/count")
def count_ballots(session: Session = Depends(get_session)):
    total = session.exec(select(func.count(Ballot.ballot_id))).one()
    return {"total_ballots": total}


# =========================================================
# Results (JOIN โชว์ชื่อไทย)
# =========================================================
@app.get("/results/constituency")
def results_constituency_by_district(session: Session = Depends(get_session)):
    statement = (
        select(
            Constituency.const_number.label("const_number"),
            Candidate.full_name.label("candidate_name"),
            Party.party_name.label("party_name"),
            func.count(Ballot.ballot_id).label("total_votes"),
        )
        .select_from(Ballot)
        .join(Constituency, Constituency.const_id == Ballot.const_id)
        .join(Candidate, Candidate.candidate_id == Ballot.candidate_id)
        .join(Party, Party.party_id == Candidate.party_id)
        .where(Ballot.vote_type == "Constituency")
        .group_by(
            Constituency.const_number,
            Candidate.full_name,
            Party.party_name,
        )
        .order_by(Constituency.const_number, func.count(Ballot.ballot_id).desc())
    )

    rows = session.exec(statement).all()
    out = []
    for r in rows:
        d = r._asdict()
        out.append({
            "เขต": f"เขต{d['const_number']}",
            "candidate_name": d["candidate_name"],
            "party_name": d["party_name"],
            "total_votes": d["total_votes"],
        })
    return out


@app.get("/results/party")
def results_party_by_district(session: Session = Depends(get_session)):
    statement = (
        select(
            Constituency.const_number.label("const_number"),
            Party.party_name.label("party_name"),
            func.count(Ballot.ballot_id).label("total_votes"),
        )
        .select_from(Ballot)
        .join(Constituency, Constituency.const_id == Ballot.const_id)
        .join(Party, Party.party_id == Ballot.party_id)
        .where(Ballot.vote_type == "PartyList")
        .group_by(
            Constituency.const_number,
            Party.party_name,
        )
        .order_by(Constituency.const_number, func.count(Ballot.ballot_id).desc())
    )

    rows = session.exec(statement).all()
    out = []
    for r in rows:
        d = r._asdict()
        out.append({
            "เขต": f"เขต{d['const_number']}",
            "party_name": d["party_name"],
            "total_votes": d["total_votes"],
        })
    return out

@app.get("/results/party/overall")
def results_party_overall(session: Session = Depends(get_session)):
    statement = (
        select(
            Ballot.party_id,
            Party.party_name.label("party_name"),
            func.count(Ballot.ballot_id).label("total_votes"),
        )
        .select_from(Ballot)
        .join(Party, Party.party_id == Ballot.party_id)
        .where(Ballot.vote_type == "PartyList")
        .group_by(Ballot.party_id, Party.party_name)
        .order_by(func.count(Ballot.ballot_id).desc())
    )

    results = session.exec(statement).all()
    return [row._asdict() for row in results]


@app.get("/results/constituency/overall")
def results_constituency_overall(session: Session = Depends(get_session)):
    statement = (
        select(
            Ballot.candidate_id,
            Candidate.full_name.label("candidate_name"),

            Candidate.party_id,
            Party.party_name.label("party_name"),

            func.count(Ballot.ballot_id).label("total_votes"),
        )
        .select_from(Ballot)
        .join(Candidate, Candidate.candidate_id == Ballot.candidate_id)
        .join(Party, Party.party_id == Candidate.party_id)
        .where(Ballot.vote_type == "Constituency")
        .group_by(
            Ballot.candidate_id,
            Candidate.full_name,
            Candidate.party_id,
            Party.party_name,
        )
        .order_by(func.count(Ballot.ballot_id).desc())
    )

    results = session.exec(statement).all()
    return [row._asdict() for row in results]