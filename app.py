from flask import Flask, render_template, request, redirect, url_for, flash
from models import (
    init_db, get_db,
    Camp, Victim,
    get_all_camps, get_camp, get_available_camps, create_camp, update_camp_resources,
    get_all_victims, get_victim, get_victims_for_camp, create_victim, update_victim_distributions,
)

app = Flask(__name__)
app.secret_key = "disaster-relief-secret-2024"


# ─── Resource distribution logic ─────────────────────────────────────────────

def distribute_resources(victim, camp):
    """
    Distribute food and medical kits to a victim.
    Critical victims are prioritised for medical kits.
    Returns (food_given, kits_given, warnings).
    """
    food_given = 0
    kits_given = 0
    warnings = []

    # One food packet per distribution call
    if camp.available_food > 0:
        food_given = 1
    else:
        warnings.append("No food packets available in this camp.")

    # Critical → always gets a medical kit if available
    # Normal   → gets kit only when supply is comfortable (≥2 remaining)
    if victim.is_critical:
        if camp.available_medical_kits > 0:
            kits_given = 1
        else:
            warnings.append("CRITICAL victim — no medical kits available in camp!")
    else:
        if camp.available_medical_kits >= 2:
            kits_given = 1

    # Apply changes
    update_camp_resources(camp.camp_id, food_delta=-food_given, kits_delta=-kits_given)
    update_victim_distributions(victim.victim_id, food_delta=food_given, kits_delta=kits_given)

    return food_given, kits_given, warnings


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    camps = get_all_camps()
    victims = get_all_victims()
    return render_template("index.html", camps=camps, victims=victims)


# ── Camps ────────────────────────────────────────────────────────────────────

@app.route("/camps")
def list_camps():
    camps = get_all_camps()
    return render_template("camps/list.html", camps=camps)


@app.route("/camps/add", methods=["GET", "POST"])
def add_camp():
    if request.method == "POST":
        try:
            location = request.form["location"].strip()
            max_capacity = int(request.form["max_capacity"])
            available_food = int(request.form.get("available_food", 0))
            available_medical_kits = int(request.form.get("available_medical_kits", 0))
            volunteers = int(request.form.get("volunteers", 0))

            if not location:
                flash("Location cannot be empty.", "danger")
                return render_template("camps/add.html")
            if max_capacity <= 0:
                flash("Max capacity must be a positive number.", "danger")
                return render_template("camps/add.html")

            camp_id = create_camp(location, max_capacity, available_food,
                                  available_medical_kits, volunteers)
            flash(f"Camp at '{location}' registered successfully! (ID: {camp_id})", "success")
            return redirect(url_for("list_camps"))

        except ValueError:
            flash("Please enter valid numeric values.", "danger")

    return render_template("camps/add.html")


@app.route("/camps/<int:camp_id>")
def view_camp(camp_id):
    camp = get_camp(camp_id)
    if not camp:
        flash("Camp not found.", "danger")
        return redirect(url_for("list_camps"))
    victims = get_victims_for_camp(camp_id)
    return render_template("camps/detail.html", camp=camp, victims=victims)


# ── Victims ──────────────────────────────────────────────────────────────────

@app.route("/victims")
def list_victims():
    victims = get_all_victims()
    # Attach camp lookup
    camps_map = {c.camp_id: c for c in get_all_camps()}
    return render_template("victims/list.html", victims=victims, camps_map=camps_map)


@app.route("/victims/register", methods=["GET", "POST"])
def register_victim():
    camps = get_available_camps()

    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            age = int(request.form["age"])
            health_condition = request.form["health_condition"]
            camp_id = int(request.form["camp_id"])

            if not name:
                flash("Name cannot be empty.", "danger")
                return render_template("victims/register.html", camps=camps)
            if age <= 0 or age > 120:
                flash("Please enter a valid age (1–120).", "danger")
                return render_template("victims/register.html", camps=camps)
            if health_condition not in ("normal", "critical"):
                flash("Health condition must be 'normal' or 'critical'.", "danger")
                return render_template("victims/register.html", camps=camps)

            camp = get_camp(camp_id)
            if not camp:
                flash("Selected camp does not exist.", "danger")
                return render_template("victims/register.html", camps=camps)
            if camp.is_full:
                flash(
                    f"Camp '{camp.location}' is full "
                    f"({camp.current_occupancy}/{camp.max_capacity}). "
                    "Please choose another camp.",
                    "danger",
                )
                return render_template("victims/register.html", camps=camps)

            # Increment occupancy first
            update_camp_resources(camp_id, occupancy_delta=1)

            # Create victim record
            victim_id = create_victim(name, age, health_condition, camp_id)
            victim = get_victim(victim_id)
            camp = get_camp(camp_id)  # refresh after occupancy update

            # Auto-distribute resources on registration
            food_given, kits_given, warnings = distribute_resources(victim, camp)

            flash(
                f"Victim '{name}' registered! (ID: {victim_id}) "
                f"| Food: {food_given} | Med Kits: {kits_given}",
                "success",
            )
            for w in warnings:
                flash(w, "warning")

            return redirect(url_for("list_victims"))

        except ValueError:
            flash("Please enter valid values.", "danger")

    return render_template("victims/register.html", camps=camps)


@app.route("/victims/search", methods=["GET", "POST"])
def search_victim():
    victim = None
    searched = False
    camp = None

    if request.method == "POST":
        searched = True
        try:
            vid = int(request.form["victim_id"])
            victim = get_victim(vid)
            if victim:
                camp = get_camp(victim.assigned_camp_id) if victim.assigned_camp_id else None
            else:
                flash(f"No victim found with ID {vid}.", "warning")
        except ValueError:
            flash("Please enter a valid numeric ID.", "danger")

    return render_template("victims/search.html", victim=victim, camp=camp, searched=searched)


# ── Distribution ─────────────────────────────────────────────────────────────

@app.route("/distribute/<int:victim_id>", methods=["POST"])
def do_distribute(victim_id):
    victim = get_victim(victim_id)
    if not victim:
        flash("Victim not found.", "danger")
        return redirect(url_for("list_victims"))

    camp = get_camp(victim.assigned_camp_id) if victim.assigned_camp_id else None
    if not camp:
        flash("Victim is not assigned to any camp.", "danger")
        return redirect(url_for("list_victims"))

    food_given, kits_given, warnings = distribute_resources(victim, camp)

    if food_given or kits_given:
        flash(
            f"Distributed to {victim.name}: {food_given} food packet(s), {kits_given} medical kit(s).",
            "success",
        )
    else:
        flash("Nothing distributed — camp resources may be depleted.", "warning")

    for w in warnings:
        flash(w, "warning")

    return redirect(request.referrer or url_for("list_victims"))


# ── Report ────────────────────────────────────────────────────────────────────

@app.route("/report")
def report():
    camps = get_all_camps()
    victims = get_all_victims()

    total_camps = len(camps)
    total_victims = len(victims)
    total_food = sum(v.food_distributed for v in victims)
    total_medical_kits = sum(v.medical_kits_distributed for v in victims)
    critical_victims = sum(1 for v in victims if v.is_critical)

    busiest_camp = max(camps, key=lambda c: c.current_occupancy) if camps else None

    camp_labels = [c.location for c in camps]
    camp_occupancy = [c.current_occupancy for c in camps]
    camp_capacity = [c.max_capacity for c in camps]

    return render_template(
        "report.html",
        total_camps=total_camps,
        total_victims=total_victims,
        total_food=total_food,
        total_medical_kits=total_medical_kits,
        critical_victims=critical_victims,
        busiest_camp=busiest_camp,
        camps=camps,
        camp_labels=camp_labels,
        camp_occupancy=camp_occupancy,
        camp_capacity=camp_capacity,
    )


# ─── Bootstrap ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
