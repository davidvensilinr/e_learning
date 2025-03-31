from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your-secret-key-here"

# File paths
USERS_FILE = "data/users.json"
COURSES_FILE = "data/courses.json"


# Helper functions
def load_data(file):
    if not os.path.exists(file):
        return []
    with open(file, "r") as f:
        return json.load(f)


def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)


def save_quiz_attempt(email, course_id, quiz_id, score, total):
    users = load_data(USERS_FILE)
    for user in users:
        if user["email"] == email:
            if "quiz_attempts" not in user:
                user["quiz_attempts"] = []
            user["quiz_attempts"].append(
                {
                    "course_id": course_id,
                    "quiz_id": quiz_id,
                    "score": score,
                    "total": total,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            save_data(USERS_FILE, users)
            break


# Routes
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        users = load_data(USERS_FILE)
        user = next(
            (u for u in users if u["email"] == email and u["password"] == password),
            None,
        )
        if user:
            session["user_email"] = email
            return redirect(url_for("dashboard"))
        flash("Invalid email or password", "danger")
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        users = load_data(USERS_FILE)

        if any(u["email"] == email for u in users):
            flash("Email already exists", "danger")
            return render_template("signup.html")

        users.append(
            {
                "name": name,
                "email": email,
                "password": password,
                "enrolled_courses": [],
                "quiz_attempts": [],
            }
        )
        save_data(USERS_FILE, users)
        session["user_email"] = email
        flash("Account created successfully!", "success")
        return redirect(url_for("dashboard"))
    return render_template("signup.html")


@app.route("/dashboard")
def dashboard():
    if "user_email" not in session:
        return redirect(url_for("login"))

    email = session["user_email"]
    users = load_data(USERS_FILE)
    user = next((u for u in users if u["email"] == email), None)

    if not user:
        return redirect(url_for("login"))

    courses = load_data(COURSES_FILE)
    return render_template(
        "dashboard.html",
        courses=courses,
        enrolled_courses=user.get("enrolled_courses", []),
        user_email=email,
    )


@app.route("/enroll/<int:course_id>", methods=["POST"])
def enroll(course_id):
    if "user_email" not in session:
        return redirect(url_for("login"))

    email = session["user_email"]
    users = load_data(USERS_FILE)
    courses = load_data(COURSES_FILE)

    if not any(c["id"] == course_id for c in courses):
        flash("Course not found", "danger")
        return redirect(url_for("dashboard"))

    for user in users:
        if user["email"] == email:
            if course_id not in user["enrolled_courses"]:
                user["enrolled_courses"].append(course_id)
                save_data(USERS_FILE, users)
                flash("Enrolled successfully!", "success")
            break

    return redirect(url_for("dashboard"))


@app.route("/course/<int:course_id>")
def course_detail(course_id):
    if "user_email" not in session:
        return redirect(url_for("login"))

    email = session["user_email"]
    users = load_data(USERS_FILE)
    user = next((u for u in users if u["email"] == email), None)

    if not user or course_id not in user.get("enrolled_courses", []):
        flash("You need to enroll in this course first", "warning")
        return redirect(url_for("dashboard"))

    courses = load_data(COURSES_FILE)
    course = next((c for c in courses if c["id"] == course_id), None)

    if not course:
        flash("Course not found", "danger")
        return redirect(url_for("dashboard"))

    return render_template(
        "course_detail.html",
        course=course,
        modules=course.get("modules", []),
        user_email=email,
    )


@app.route("/reading/<reading_id>")
def reading_page(reading_id):
    if "user_email" not in session:
        return redirect(url_for("login"))

    courses = load_data(COURSES_FILE)

    for course in courses:
        for module in course.get("modules", []):
            if module.get("reading", {}).get("url") == f"reading/{reading_id}":
                return render_template(
                    "reading.html",
                    content=module["reading"]["content"],
                    title=module["reading"]["title"],
                    course_title=course["title"],
                    course_id=course["id"],
                )

    flash("Reading material not found", "danger")
    return redirect(url_for("dashboard"))


@app.route("/quiz/<quiz_id>", methods=["GET", "POST"])
def quiz_page(quiz_id):
    if "user_email" not in session:
        return redirect(url_for("login"))

    courses = load_data(COURSES_FILE)
    quiz_data = None
    course_id = None

    for course in courses:
        for module in course.get("modules", []):
            if module.get("assessment", {}).get("url") == f"quiz/{quiz_id}":
                quiz_data = module["assessment"]
                course_id = course["id"]
                break
        if quiz_data:
            break

    if not quiz_data:
        flash("Quiz not found", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        return handle_quiz_submission(quiz_data, course_id)

    return render_template("quiz.html", quiz=quiz_data, course_id=course_id)


def handle_quiz_submission(quiz, course_id):
    score = 0
    user_answers = {}

    for i, question in enumerate(quiz["questions"]):
        if question.get("type") == "multiple":
            # Get all selected options as integers
            selected = request.form.getlist(f"q{i+1}")
            user_answers[i] = [int(x) for x in selected] if selected else []

            # Convert correct answers to set for comparison
            correct_answers = set(question.get("answers", []))
            user_selected = set(user_answers[i])

            # Only mark correct if EXACT match (no partial credit)
            if user_selected == correct_answers:
                score += 1
        else:
            # Single answer question
            user_answer = request.form.get(f"q{i+1}")
            user_answers[i] = int(user_answer) if user_answer else -1
            if user_answers[i] == question.get("answer", -2):
                score += 1

    total = len(quiz["questions"])
    grade = (score / total) * 100
    passed = grade >= quiz.get("passing_grade", 70)

    save_quiz_attempt(
        session["user_email"], course_id, quiz["url"].split("/")[-1], score, total
    )

    # Prepare question data for template
    for i, question in enumerate(quiz["questions"]):
        question["user_answer"] = user_answers[i]
        if question.get("type") == "multiple":
            question["is_correct"] = set(user_answers[i]) == set(
                question.get("answers", [])
            )
        else:
            question["is_correct"] = user_answers[i] == question.get("answer", -2)

    return render_template(
        "quiz_result.html",
        quiz=quiz,
        score=score,
        total=total,
        grade=grade,
        passed=passed,
        course_id=course_id,
    )


@app.route("/logout")
def logout():
    session.pop("user_email", None)
    flash("You have been logged out", "info")
    return redirect(url_for("login"))


if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(USERS_FILE):
        save_data(USERS_FILE, [])
    if not os.path.exists(COURSES_FILE):
        save_data(COURSES_FILE, [])
    app.run(debug=True)
