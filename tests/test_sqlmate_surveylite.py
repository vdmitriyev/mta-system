"""sqlmate and SurveyLite: accounts, surveys of the users, services that wait for a survey"""

import pytest

from app import provisioning, surveys
from app.models import SqlmateService, SurveyAssignment, SurveyliteService
from app.services import sqlmate_api, surveylite_api
from app.services.surveylite_api import Survey, SurveyLink
from tests.conftest import post, switch_on

BASE = "https://mtas.example.org/surveylite"
SURVEY = Survey(id=7, title="Entry survey", status="active", require_login=True)
OTHER = Survey(id=8, title="Feedback", status="active")


class FakeSurveyLite:
    """surveylite with participants, surveys and the status of each link"""

    def __init__(self):
        self.surveys = [SURVEY, OTHER]
        self.participants = 0
        self.links = {}  # (participant, survey) -> status
        self.keys = {}  # participant -> number of the login key
        # False: SurveyLite before 0.21.0, without login links
        self.login_links = True
        self.down = False

    def _check(self):
        if self.down:
            raise surveylite_api.SurveyliteError("surveylite is not reachable")

    def list_surveys(self):
        self._check()
        return list(self.surveys)

    def create_participant(self, *args, **kwargs):
        self._check()
        # the app sends nothing about the user
        assert not args and not kwargs
        self.participants += 1
        number = self.participants
        self.keys[f"p{number}"] = 1
        return surveylite_api.Participant(
            id=f"p{number}",
            login=f"bison.nice{number}",
            pin=f"55555{number}",
            dashboard_url=f"{BASE}/me",
            login_url=self._login_url(f"p{number}"),
        )

    def _key(self, participant):
        return f"key-{participant}-{self.keys[participant]}"

    def _login_url(self, participant):
        if not self.login_links:
            return None
        return f"{BASE}/me?auth={self._key(participant)}"

    def login_link(self, participant_id, renew=False):
        self._check()
        if not self.login_links:
            raise surveylite_api.SurveyliteError("surveylite answered 404: Not Found")
        if renew:
            self.keys[participant_id] += 1
        return f"{BASE}/me?auth={self._key(participant_id)}"

    def _link(self, participant, survey_id):
        url = f"{BASE}/s/{participant}-{survey_id}"
        return SurveyLink(
            survey_id=survey_id,
            url=url,
            status=self.links[(participant, survey_id)],
            participant_id=participant,
            auth_url=(
                f"{url}?auth={self._key(participant)}" if self.login_links else None
            ),
        )

    def assign(self, survey_id, participant_ids):
        self._check()
        for participant in participant_ids:
            self.links.setdefault((participant, survey_id), "not_started")
        return [self._link(p, survey_id) for p in participant_ids]

    def participant_links(self, participant_id):
        self._check()
        return [
            self._link(participant, survey_id)
            for participant, survey_id in self.links
            if participant == participant_id
        ]


@pytest.fixture
def surveylite(monkeypatch):
    fake = FakeSurveyLite()
    for name in (
        "list_surveys",
        "create_participant",
        "assign",
        "participant_links",
        "login_link",
    ):
        monkeypatch.setattr(surveylite_api, name, getattr(fake, name))
    return fake


@pytest.fixture
def sqlmate(monkeypatch):
    calls = []

    def create_user(email):
        calls.append(email)
        return sqlmate_api.SqlmateAccount(
            login=email,
            pin="4321",
            login_url="https://mtas.example.org/sqlmate/login?uHash=u&pHash=p",
            created=True,
        )

    monkeypatch.setattr(sqlmate_api, "create_user", create_user)
    monkeypatch.setattr(sqlmate_api, "ping", lambda: "mta-system")
    return calls


def add_sqlmate(db, user):
    entry = SqlmateService(
        user_id=user.itid,
        sqlmate_login=user.internal_email,
        sqlmate_pin="4321",
        sqlmate_login_url="https://mtas.example.org/sqlmate/login?uHash=u&pHash=p",
        created=True,
    )
    db.add(entry)
    db.commit()
    return entry


# ---------- provisioning ----------


def test_sqlmate_account_with_the_internal_email(db, student, sqlmate):
    switch_on(db, "sqlmate")
    assert provisioning.sqlmate_user(db, student.itid, student.internal_email)
    entry = db.query(SqlmateService).one()
    assert sqlmate == [student.internal_email]
    assert (entry.sqlmate_pin, entry.created) == ("4321", True)
    assert entry.sqlmate_login_url.endswith("uHash=u&pHash=p")


def test_sqlmate_is_skipped_when_switched_off(db, student, sqlmate):
    assert provisioning.sqlmate_user(db, student.itid, "x@y.z") is False
    assert sqlmate == [] and db.query(SqlmateService).count() == 0


def test_sqlmate_errors_keep_the_registration_going(db, student, monkeypatch):
    def fail(email):
        raise sqlmate_api.SqlmateError("sqlmate is not reachable")

    monkeypatch.setattr(sqlmate_api, "create_user", fail)
    assert not provisioning.sqlmate_user(db, student.itid, "x@y.z", force_create=True)
    assert db.query(SqlmateService).one().created is False


def test_participant_is_anonymous_and_gets_the_needed_surveys(db, student, surveylite):
    surveys.set_requirement(db, "sqlmate", SURVEY)
    switch_on(db, "surveylite")
    assert provisioning.surveylite_participant(db, student.itid)

    entry = db.query(SurveyliteService).one()
    assert (entry.surveylite_participant_id, entry.surveylite_login) == (
        "p1",
        "bison.nice1",
    )
    # only this table links the user and the participant
    row = db.query(SurveyAssignment).one()
    assert (row.user_id, row.survey_id, row.status) == (student.itid, 7, "not_started")
    assert row.survey_url == f"{BASE}/s/p1-7"
    assert row.survey_auth_url == f"{BASE}/s/p1-7?auth=key-p1-1"
    assert entry.surveylite_login_url == f"{BASE}/me?auth=key-p1-1"


def test_registration_creates_both_accounts(db, sqlmate, surveylite, no_email):
    from app.users import register_new_user

    switch_on(db, "sqlmate", "surveylite")
    user = register_new_user(db, "new.student@uni.example")
    assert sqlmate == [user.internal_email]
    assert db.query(SurveyliteService).filter_by(user_id=user.itid).count() == 1


# ---------- services page ----------


def test_services_page_shows_sqlmate_and_surveylite(
    student_client, db, student, surveylite
):
    add_sqlmate(db, student)
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    surveys.assign_survey(db, SURVEY, [student.itid])

    text = student_client.get("/services").text
    sqlmate_card = text[text.index('id="service-sqlmate"') :]
    sqlmate_card = sqlmate_card[: sqlmate_card.index("</section>")]
    assert "Log in to sqlmate" in sqlmate_card
    assert 'href="https://mtas.example.org/sqlmate/login?uHash=u&amp;pHash=p"' in (
        sqlmate_card
    )
    assert student.internal_email in sqlmate_card
    assert 'data-secret="4321"' in sqlmate_card
    assert "https://mtas.example.org/sqlmate/" in sqlmate_card

    survey_card = text[text.index('id="service-surveylite"') :]
    survey_card = survey_card[: survey_card.index("</section>")]
    assert "https://mtas.example.org/surveylite/me" in survey_card
    assert "bison.nice1" in survey_card and 'data-secret="555551"' in survey_card
    # one click: the login link and the survey link that also logs in
    assert "Log in to SurveyLite" in survey_card
    assert f'href="{BASE}/me?auth=key-p1-1"' in survey_card
    assert f'href="{BASE}/s/p1-7?auth=key-p1-1"' in survey_card
    assert "Entry survey" in survey_card and "not started" in survey_card


@pytest.mark.parametrize(
    "link",
    [
        "https://mtas.example.org/me?auth=key-1",
        "http://surveylite-service:5001/me?auth=key-1",
        "https://mtas.example.org/surveylite/me?auth=key-1",
    ],
)
def test_links_of_surveylite_use_its_public_address(settings, link):
    assert surveys.public_link(link) == f"{BASE}/me?auth=key-1"


def test_public_link_keeps_the_survey_path(settings):
    assert surveys.public_link("https://mtas.example.org/s/p1-7") == f"{BASE}/s/p1-7"
    assert surveys.public_link(None) is None


def test_services_page_fixes_a_login_link_without_the_prefix(
    student_client, db, student, surveylite
):
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    entry = surveys.participant_of(db, student.itid)
    entry.surveylite_login_url = "https://mtas.example.org/me?auth=key-p1-1"
    db.commit()

    text = student_client.get("/services").text
    assert f'href="{BASE}/me?auth=key-p1-1"' in text
    assert 'href="https://mtas.example.org/me?auth=' not in text


def test_sqlmate_waits_for_the_survey(student_client, db, student, surveylite):
    add_sqlmate(db, student)
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    surveys.set_requirement(db, "sqlmate", SURVEY)
    surveys.assign_survey(db, SURVEY, [student.itid])

    text = student_client.get("/services").text
    card = text[text.index('id="service-sqlmate"') :]
    card = card[: card.index("</section>")]
    assert "Complete the survey" in card
    assert f'href="{BASE}/s/p1-7?auth=key-p1-1"' in card
    assert "4321" not in card and "Log in to sqlmate" not in card

    # the user completes the survey in surveylite
    surveylite.links[("p1", 7)] = "completed"
    text = student_client.get("/services").text
    card = text[text.index('id="service-sqlmate"') :]
    card = card[: card.index("</section>")]
    assert "Complete the survey" not in card
    assert 'data-secret="4321"' in card
    assert db.query(SurveyAssignment).one().completed_at is not None


def test_older_surveylite_without_login_links(student_client, db, student, surveylite):
    surveylite.login_links = False
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    surveys.assign_survey(db, SURVEY, [student.itid])

    text = student_client.get("/services").text
    card = text[text.index('id="service-surveylite"') :]
    card = card[: card.index("</section>")]
    assert "Log in to SurveyLite" not in card
    assert f'href="{BASE}/s/p1-7"' in card


def test_login_link_is_read_for_older_participants(
    student_client, db, student, surveylite
):
    surveylite.login_links = False
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    surveylite.login_links = True  # SurveyLite was updated

    student_client.get("/services")
    db.expire_all()
    entry = surveys.participant_of(db, student.itid)
    assert entry.surveylite_login_url == f"{BASE}/me?auth=key-p1-1"


def test_survey_not_given_blocks_the_service(student_client, db, student):
    add_sqlmate(db, student)
    surveys.set_requirement(db, "sqlmate", SURVEY)
    text = student_client.get("/services").text
    assert "The survey is not set up for you yet" in text
    assert "4321" not in text


def test_last_known_status_counts_when_surveylite_is_down(
    student_client, db, student, surveylite
):
    add_sqlmate(db, student)
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    surveys.set_requirement(db, "sqlmate", SURVEY)
    surveys.assign_survey(db, SURVEY, [student.itid])
    surveylite.links[("p1", 7)] = "completed"
    surveys.refresh_user(db, student.itid)

    surveylite.down = True
    text = student_client.get("/services").text
    assert 'data-secret="4321"' in text


# ---------- admin pages ----------


def test_admin_gives_a_survey_to_all_users(admin_client, db, student, surveylite):
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    text = admin_client.get("/mtas-admin/services/surveylite").text
    assert "Entry survey" in text and "Feedback" in text
    assert "bison.nice1" in text

    post(
        admin_client,
        "/mtas-admin/services/surveylite/assign",
        {"survey_id": 8, "user_id": "all"},
    )
    text = admin_client.get("/mtas-admin/services/surveylite").text
    # the admin has no participant
    assert "was given to 1 users" in text and "1 users have no SurveyLite" in text
    assert db.query(SurveyAssignment).one().survey_id == 8


def test_admin_sets_and_clears_a_requirement(admin_client, db, surveylite):
    post(
        admin_client,
        "/mtas-admin/services/surveylite/requirement",
        {"service": "sqlmate", "survey_id": "7"},
    )
    assert surveys.requirements(db)["sqlmate"].survey_title == "Entry survey"
    text = admin_client.get("/mtas-admin/services/surveylite").text
    assert '<option value="7" selected>Entry survey</option>' in text

    post(
        admin_client,
        "/mtas-admin/services/surveylite/requirement",
        {"service": "sqlmate", "survey_id": ""},
    )
    db.expire_all()
    assert surveys.requirements(db) == {}


@pytest.mark.parametrize("service", ["surveylite", "nifi", "oracle"])
def test_requirement_only_for_open_services(admin_client, db, surveylite, service):
    post(
        admin_client,
        "/mtas-admin/services/surveylite/requirement",
        {"service": service, "survey_id": "7"},
    )
    assert surveys.requirements(db) == {}


def test_admin_creates_a_participant_and_reads_the_status(
    admin_client, db, student, surveylite
):
    post(
        admin_client,
        "/mtas-admin/services/surveylite/participant",
        {"user_id": student.itid},
    )
    assert surveys.participant_of(db, student.itid).surveylite_login == "bison.nice1"
    surveys.assign_survey(db, SURVEY, [student.itid])
    surveylite.links[("p1", 7)] = "completed"
    post(admin_client, "/mtas-admin/services/surveylite/refresh")
    db.expire_all()
    assert db.query(SurveyAssignment).one().status == "completed"


def test_admin_renews_the_login_link(admin_client, db, student, surveylite):
    provisioning.surveylite_participant(db, student.itid, force_create=True)
    surveys.assign_survey(db, SURVEY, [student.itid])
    text = admin_client.get("/mtas-admin/services/surveylite").text
    assert "New login link" in text and "login needed" in text

    post(
        admin_client,
        "/mtas-admin/services/surveylite/login-link",
        {"user_id": student.itid},
    )
    db.expire_all()
    assert surveys.participant_of(db, student.itid).surveylite_login_url.endswith(
        "auth=key-p1-2"
    )
    # the survey links with login carry the new key, too
    assert db.query(SurveyAssignment).one().survey_auth_url.endswith("auth=key-p1-2")
    text = admin_client.get("/mtas-admin/services/surveylite").text
    assert "has a new login link" in text


def test_surveylite_page_without_surveylite(admin_client, surveylite):
    surveylite.down = True
    text = admin_client.get("/mtas-admin/services/surveylite").text
    assert "The API of SurveyLite does not answer" in text
    assert "surveylite is not reachable" in text


def test_admin_creates_a_sqlmate_account(admin_client, db, student, sqlmate):
    text = admin_client.get("/mtas-admin/services/sqlmate").text
    assert "API key “mta-system” works" in text
    post(admin_client, "/mtas-admin/services/sqlmate/create", {"user_id": student.itid})
    assert sqlmate == [student.internal_email]
    text = admin_client.get("/mtas-admin/services/sqlmate").text
    assert "sqlmate was set up for" in text


def test_sqlmate_page_without_api_key(admin_client):
    text = admin_client.get("/mtas-admin/services/sqlmate").text
    assert "SQLMATE_API_KEY is not set" in text


@pytest.mark.parametrize(
    "path",
    [
        "/mtas-admin/services/sqlmate/create",
        "/mtas-admin/services/surveylite/assign",
        "/mtas-admin/services/surveylite/requirement",
        "/mtas-admin/services/surveylite/participant",
        "/mtas-admin/services/surveylite/refresh",
    ],
)
def test_students_cannot_use_the_admin_actions(student_client, path):
    response = student_client.post(path, follow_redirects=False)
    assert response.status_code in (303, 403, 404)


@pytest.mark.parametrize("page", ["sqlmate", "surveylite"])
def test_pages_are_in_the_services_menu(admin_client, surveylite, page):
    text = admin_client.get(f"/mtas-admin/services/{page}").text
    assert f'href="/mtas-admin/services/{page}" aria-current="page"' in text


# ---------- clients ----------


def test_clients_need_an_api_key(settings):
    with pytest.raises(sqlmate_api.SqlmateError, match="SQLMATE_API_KEY"):
        sqlmate_api.ping()
    with pytest.raises(surveylite_api.SurveyliteError, match="SURVEYLITE_API_KEY"):
        surveylite_api.list_surveys()


def test_clients_send_the_key(use_settings, monkeypatch):
    use_settings(
        SQLMATE_API_KEY="sm-key",
        SURVEYLITE_API_KEY="sl-key",
        SURVEYLITE_API_URL="http://surveylite:5001/api/v1/",
    )
    seen = []

    class Answer:
        status_code = 200

        def json(self):
            return [{"id": 1, "title": "T", "status": "active", "slug": "t"}]

    def fake_request(method, url, headers, timeout, **kwargs):
        seen.append((method, url, headers))
        return Answer()

    monkeypatch.setattr(surveylite_api.requests, "request", fake_request)
    assert surveylite_api.list_surveys() == [Survey(1, "T", "active", "t")]
    assert seen == [
        ("GET", "http://surveylite:5001/api/v1/surveys", {"X-API-Key": "sl-key"})
    ]
