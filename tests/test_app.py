import re

from tests.conftest import Client


def add_meal(client: Client, name: str, meal_type: str, ingredients: str = ""):
    r = client.submit(
        "/meals",
        {"name": name, "meal_type": meal_type, "ingredients": ingredients, "description": ""},
        csrf_from="/meals/new",
    )
    assert r.status_code == 303, r.text


def plan_id_from(response) -> int:
    return int(re.search(r"/plans/(\d+)", response.headers["location"]).group(1))


def test_requires_login(client):
    r = client.get("/meals")
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=/meals"


def test_post_without_csrf_is_rejected(logged_in):
    r = logged_in.post("/meals", data={"name": "X", "meal_type": "meat"})
    assert r.status_code == 400


def test_login_logout(client):
    client.submit("/register", {"username": "Ana", "password": "password123", "password_confirm": "password123"})
    client.submit("/logout", {}, csrf_from="/")
    assert client.get("/").status_code == 303
    bad = client.submit("/login", {"username": "ana", "password": "wrong"})
    assert bad.status_code == 400
    ok = client.submit("/login", {"username": "ANA", "password": "password123"})
    assert ok.status_code == 303
    assert client.get("/").status_code == 200


def test_generate_edit_and_share_plan(logged_in):
    for i in range(4):
        add_meal(logged_in, f"Steak {i}", "meat", "Beef\nPotatoes")
        add_meal(logged_in, f"Cod {i}", "fish", "Cod\nPotatoes")
        add_meal(logged_in, f"Veggie lasagne {i}", "vegetarian")

    data = [("week", "next"), ("mode", "random"), ("meals_per_day", "1"), ("name", "Teste"),
            ("type_meat", "2"), ("type_fish", "3"), ("type_vegetarian", "")]
    data += [("days", str(i)) for i in range(7)]
    r = logged_in.submit("/plans", data, csrf_from="/plans/new")
    assert r.status_code == 303, r.text
    plan_id = plan_id_from(r)

    page = logged_in.get(f"/plans/{plan_id}").text
    assert page.count("tag tag-meat") == 2
    assert page.count("tag tag-fish") == 3
    assert "Shopping list" in page

    share_path = re.search(r"/p/[0-9a-f-]{36}", page).group(0)

    # Public view works without a session
    anon = Client(logged_in.app)
    shared = anon.get(share_path)
    assert shared.status_code == 200
    assert "Teste" in shared.text and 'og:image' in shared.text
    image = anon.get(f"{share_path}/plan.png")
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    assert anon.get("/p/00000000-0000-0000-0000-000000000000").status_code == 404
    assert anon.get("/p/not-a-uuid").status_code == 404

    # Manually set the first entry to "Por definir", then reroll it
    entry_ids = re.findall(r'name="entry-(\d+)"', page)
    r = logged_in.submit(f"/plans/{plan_id}/entries", {f"entry-{entry_ids[0]}": ""}, csrf_from=f"/plans/{plan_id}")
    assert r.status_code == 303
    assert "is-empty" in logged_in.get(f"/plans/{plan_id}").text
    r = logged_in.submit(f"/plans/{plan_id}/entries/{entry_ids[0]}/reroll", {}, csrf_from=f"/plans/{plan_id}")
    assert r.status_code == 303

    # Regenerate and rotate share link
    assert logged_in.submit(f"/plans/{plan_id}/regenerate", {}, csrf_from=f"/plans/{plan_id}").status_code == 303
    assert logged_in.submit(f"/plans/{plan_id}/share/rotate", {}, csrf_from=f"/plans/{plan_id}").status_code == 303
    assert anon.get(share_path).status_code == 404


def test_infeasible_constraints_show_error(logged_in):
    add_meal(logged_in, "Chicken", "meat")
    data = [("week", "current"), ("mode", "random"), ("meals_per_day", "1"), ("days", "0"), ("type_fish", "1")]
    r = logged_in.submit("/plans", data, csrf_from="/plans/new")
    assert r.status_code == 400
    assert "you have no fish meals saved" in r.text


def test_manual_plan_and_deleted_meal_keeps_name(logged_in):
    add_meal(logged_in, "Octopus", "fish")
    r = logged_in.submit("/plans", [("week", "current"), ("mode", "manual"), ("days", "2")], csrf_from="/plans/new")
    plan_id = plan_id_from(r)
    page = logged_in.get(f"/plans/{plan_id}").text
    entry_id = re.search(r'name="entry-(\d+)"', page).group(1)
    meal_id = re.search(r'<option value="(\d+)"', page).group(1)
    logged_in.submit(f"/plans/{plan_id}/entries", {f"entry-{entry_id}": meal_id}, csrf_from=f"/plans/{plan_id}")

    logged_in.submit(f"/meals/{meal_id}/delete", {}, csrf_from="/meals")
    page = logged_in.get(f"/plans/{plan_id}").text
    assert "Octopus (deleted)" in page
    # Saving the form again must not wipe the snapshot
    logged_in.submit(f"/plans/{plan_id}/entries", {f"entry-{entry_id}": "keep"}, csrf_from=f"/plans/{plan_id}")
    assert "Octopus" in logged_in.get(f"/plans/{plan_id}").text


def test_users_cannot_see_each_others_data(logged_in):
    add_meal(logged_in, "Secret stew", "meat")
    r = logged_in.submit("/plans", [("week", "current"), ("mode", "random"), ("days", "0")], csrf_from="/plans/new")
    plan_id = plan_id_from(r)
    meal_id = re.search(r"/meals/(\d+)/edit", logged_in.get("/meals").text).group(1)

    other = Client(logged_in.app, follow_redirects=False)
    other.submit("/register", {"username": "intruder", "password": "password123", "password_confirm": "password123"})
    assert "Secret stew" not in other.get("/meals").text
    assert other.get(f"/plans/{plan_id}").status_code == 404
    assert other.get(f"/meals/{meal_id}/edit").status_code == 404
    assert other.submit(f"/plans/{plan_id}/delete", {}, csrf_from="/").status_code == 404


def test_skip_a_day(logged_in):
    add_meal(logged_in, "Risotto", "vegetarian", "Rice")
    r = logged_in.submit("/plans", [("week", "next"), ("mode", "random"), ("days", "0"), ("days", "1")], csrf_from="/plans/new")
    plan_id = plan_id_from(r)
    page = logged_in.get(f"/plans/{plan_id}").text
    first, second = re.findall(r'name="entry-(\d+)"', page)

    logged_in.submit(f"/plans/{plan_id}/entries", {f"entry-{first}": "skip"}, csrf_from=f"/plans/{plan_id}")
    page = logged_in.get(f"/plans/{plan_id}").text
    assert '<option value="skip" selected>' in page
    share_path = re.search(r"/p/[0-9a-f-]{36}", page).group(0)
    shared = Client(logged_in.app).get(share_path).text
    assert "Nothing planned" in shared and "Risotto" in shared
    assert Client(logged_in.app).get(f"{share_path}/plan.png").status_code == 200

    # Picking a dish again clears the skip; rerolling a skipped slot fills it
    logged_in.submit(f"/plans/{plan_id}/entries", {f"entry-{second}": "skip"}, csrf_from=f"/plans/{plan_id}")
    logged_in.submit(f"/plans/{plan_id}/entries/{second}/reroll", {}, csrf_from=f"/plans/{plan_id}")
    page = logged_in.get(f"/plans/{plan_id}").text
    assert page.count('<option value="skip" selected>') == 1
