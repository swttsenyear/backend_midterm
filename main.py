from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, select, func
from sqlalchemy.orm import aliased
from typing import List

from database import create_db_and_tables, get_session
from models import Region, Constituency, Party, Candidate, Voter, Ballot

from contextlib import asynccontextmanager


# =========================
# Startup
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(title="Election Backend Midterm", lifespan=lifespan)


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


@app.get("/voters")
def get_voters(session: Session = Depends(get_session)):
    statement = (
        select(
            Voter.citizen_id,
            Voter.full_name,
            Constituency.const_number,
            Voter.has_voted_const,
            Voter.has_voted_list,
        )
        .join(Constituency, Constituency.const_id == Voter.const_id)
        .order_by(Constituency.const_number)
    )

    rows = session.exec(statement).all()

    return [
        {
            "citizen_id": r.citizen_id,
            "full_name": r.full_name,
            "เขตเลือกตั้ง": f"เขต {r.const_number}",

            # ✔ ใช้สิทธิแล้วทั้งบัตรดีและเสีย
            "บัตรเขต": "ใช้สิทธิแล้ว" if r.has_voted_const else "ยังไม่ใช้สิทธิ",
            "บัตรพรรค": "ใช้สิทธิแล้ว" if r.has_voted_list else "ยังไม่ใช้สิทธิ",
        }
        for r in rows
    ]

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
    voter = session.get(Voter, ballot.voter_id)
    if not voter:
        raise HTTPException(status_code=404, detail="Voter not found")

    # voter ต้องอยู่เขตเดียวกับ ballot (ถ้าผิด = บัตรเสีย แต่ยังเก็บ)
    if voter.const_id != ballot.const_id:
        ballot.is_valid = False

    # vote_type ถ้าไม่ใช่ 2 แบบนี้ จะ “เก็บเป็นบัตรเสีย” (ไม่ 400)
    if ballot.vote_type not in ["Constituency", "PartyList"]:
        ballot.is_valid = False
        # ไม่รู้จะ update flag อะไร -> ไม่อัปเดตสถานะโหวต
        session.add(ballot)
        session.commit()
        session.refresh(ballot)
        return ballot

    # -------- ตัดสินบัตรดี/เสียจากรูปแบบข้อมูล --------
    if ballot.vote_type == "Constituency":
        # กันโหวตซ้ำ (ยังกันเหมือนเดิม)
        if voter.has_voted_const:
            raise HTTPException(status_code=400, detail="Already voted constituency")

        # เงื่อนไขบัตรดี: ต้องมี candidate_id และต้องไม่มี party_id
        good = (ballot.candidate_id is not None) and (ballot.party_id is None)

        # ตรวจ candidate ถ้าจะเป็นบัตรดี
        if good:
            candidate = session.get(Candidate, ballot.candidate_id)
            if not candidate or candidate.const_id != ballot.const_id:
                good = False

        ballot.is_valid = bool(good)

        # บัตรเสีย: ทำให้ช่องที่ไม่ควรมีเป็น None (กันข้อมูลเลอะ)
        if not ballot.is_valid:
            ballot.party_id = None
            # จะให้ candidate_id ค้างไว้หรือไม่ก็ได้; แนะนำล้างเพื่อ privacy/clean
            ballot.candidate_id = None

        # ถือว่าใช้สิทธิแล้ว (แม้บัตรเสียก็ใช้สิทธิแล้วในชีวิตจริง)
        voter.has_voted_const = 1

    elif ballot.vote_type == "PartyList":
        if voter.has_voted_list:
            raise HTTPException(status_code=400, detail="Already voted party list")

        # เงื่อนไขบัตรดี: ต้องมี party_id และต้องไม่มี candidate_id
        good = (ballot.party_id is not None) and (ballot.candidate_id is None)

        if good:
            party = session.get(Party, ballot.party_id)
            if not party:
                good = False

        ballot.is_valid = bool(good)

        if not ballot.is_valid:
            ballot.candidate_id = None
            ballot.party_id = None

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


    statement = (
        select(
            Ballot.ballot_id,
            Ballot.vote_type,
            Ballot.voted_at,
            Ballot.is_valid,

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
            "ballot_note": "บัตรดี" if d["is_valid"] else "บัตรเสีย",
            "vote_type": d["vote_type"],
        }

        if d["is_valid"]:
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

@app.get("/ballots/summary")
def ballots_summary(session: Session = Depends(get_session)):
    total = session.exec(select(func.count(Ballot.ballot_id))).one()

    valid_count = session.exec(
        select(func.count(Ballot.ballot_id)).where(Ballot.is_valid == True)
    ).one()

    invalid_count = session.exec(
        select(func.count(Ballot.ballot_id)).where(Ballot.is_valid == False)
    ).one()

    valid_const = session.exec(
        select(func.count(Ballot.ballot_id)).where(
            Ballot.is_valid == True, Ballot.vote_type == "Constituency"
        )
    ).one()

    valid_party = session.exec(
        select(func.count(Ballot.ballot_id)).where(
            Ballot.is_valid == True, Ballot.vote_type == "PartyList"
        )
    ).one()

    invalid_const = session.exec(
        select(func.count(Ballot.ballot_id)).where(
            Ballot.is_valid == False, Ballot.vote_type == "Constituency"
        )
    ).one()

    invalid_party = session.exec(
        select(func.count(Ballot.ballot_id)).where(
            Ballot.is_valid == False, Ballot.vote_type == "PartyList"
        )
    ).one()

    return {
        "total_ballots": total,
        "valid_ballots": valid_count,
        "invalid_ballots": invalid_count,
        "valid_constituency": valid_const,
        "valid_partylist": valid_party,
        "invalid_constituency": invalid_const,
        "invalid_partylist": invalid_party,
    }

@app.get("/ballots/validity-count")
def ballots_validity_count(session: Session = Depends(get_session)):
    good = session.exec(
        select(func.count(Ballot.ballot_id)).where(Ballot.is_valid == True)
    ).one()

    bad = session.exec(
        select(func.count(Ballot.ballot_id)).where(Ballot.is_valid == False)
    ).one()

    return {
        "บัตรดี": good,
        "บัตรเสีย": bad
    }
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
        .where(
            Ballot.vote_type == "Constituency",
            Ballot.is_valid == True
        )
        .group_by(
            Constituency.const_number,
            Candidate.full_name,
            Party.party_name,
        )
        .order_by(Constituency.const_number, func.count(Ballot.ballot_id).desc())
    )

    rows = session.exec(statement).all()
    return [
        {
            "เขต": f"เขต{r.const_number}",
            "ผู้สมัคร": r.candidate_name,
            "พรรค": r.party_name,
            "คะแนน": r.total_votes,
        }
        for r in rows
    ]

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
        .where(
            Ballot.vote_type == "PartyList",
            Ballot.is_valid == True
        )
        .group_by(
            Constituency.const_number,
            Party.party_name,
        )
        .order_by(Constituency.const_number, func.count(Ballot.ballot_id).desc())
    )

    rows = session.exec(statement).all()
    return [
        {
            "เขต": f"เขต{r.const_number}",
            "พรรค": r.party_name,
            "คะแนน": r.total_votes,
        }
        for r in rows
    ]

@app.get("/results/constituency/overall")
def results_constituency_overall(session: Session = Depends(get_session)):
    statement = (
        select(
            Candidate.full_name.label("candidate_name"),
            Party.party_name.label("party_name"),
            func.count(Ballot.ballot_id).label("total_votes"),
        )
        .select_from(Ballot)
        .join(Candidate, Candidate.candidate_id == Ballot.candidate_id)
        .join(Party, Party.party_id == Candidate.party_id)
        .where(
            Ballot.vote_type == "Constituency",
            Ballot.is_valid == True
        )
        .group_by(Candidate.full_name, Party.party_name)
        .order_by(func.count(Ballot.ballot_id).desc())
    )

    rows = session.exec(statement).all()
    return [{"ผู้สมัคร": r.candidate_name, "พรรค": r.party_name, "คะแนน": r.total_votes} for r in rows]


@app.get("/results/party/overall")
def results_party_overall(session: Session = Depends(get_session)):
    statement = (
        select(
            Party.party_name.label("party_name"),
            func.count(Ballot.ballot_id).label("total_votes"),
        )
        .select_from(Ballot)
        .join(Party, Party.party_id == Ballot.party_id)
        .where(
            Ballot.vote_type == "PartyList",
            Ballot.is_valid == True
        )
        .group_by(Party.party_name)
        .order_by(func.count(Ballot.ballot_id).desc())
    )

    rows = session.exec(statement).all()
    return [{"พรรค": r.party_name, "คะแนน": r.total_votes} for r in rows]