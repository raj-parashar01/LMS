import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import get_db
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date, datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")


# Auto-increment integer ID helper (taaki HTML templates bina badle kaam karein)
def get_next_id(db, collection_name):
    last_doc = db[collection_name].find_one(sort=[("id", -1)])
    return (last_doc["id"] + 1) if last_doc and "id" in last_doc else 1


# Create default admin account
def create_admin():
    db = get_db()
    if not db.users.find_one({"username": "admin"}):
        admin_pass = os.environ.get("ADMIN_PASSWORD", "Admin@123")
        password = generate_password_hash(admin_pass)
        db.users.insert_one({
            "id": get_next_id(db, "users"),
            "username": "admin",
            "password": password
        })


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


# Login
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    create_admin()  # Vercel par pehli baar default admin bana dega

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.users.find_one({"username": username})

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        flash("Invalid username or password", "danger")

    return render_template("login.html")


# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# Dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()

    total_books = db.books.count_documents({})
    total_students = db.students.count_documents({})
    issued_books = db.issued_books.count_documents({"status": "Issued"})

    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$quantity"}}}]
    agg_result = list(db.books.aggregate(pipeline))
    available_books = agg_result[0]["total"] if agg_result else 0

    return render_template(
        "dashboard.html",
        total_books=total_books,
        total_students=total_students,
        issued_books=issued_books,
        available_books=available_books
    )


# Books
@app.route("/books", methods=["GET", "POST"])
@login_required
def books():
    db = get_db()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()

        try:
            quantity = int(request.form.get("quantity", -1))
        except ValueError:
            quantity = -1

        if title and author and quantity >= 0:
            db.books.insert_one({
                "id": get_next_id(db, "books"),
                "title": title,
                "author": author,
                "category": category,
                "quantity": quantity
            })
            flash("Book added successfully", "success")
        else:
            flash("Please enter valid book details", "danger")

        return redirect(url_for("books"))

    search = request.args.get("search", "").strip()
    query = {}
    if search:
        query = {
            "$or": [
                {"title": {"$regex": search, "$options": "i"}},
                {"author": {"$regex": search, "$options": "i"}}
            ]
        }

    book_list = list(db.books.find(query).sort("id", -1))
    return render_template("books.html", books=book_list, search=search)


@app.route("/delete_book/<int:id>", methods=["POST"])
@login_required
def delete_book(id):
    db = get_db()

    try:
        if db.issued_books.find_one({"book_id": id, "status": "Issued"}):
            flash("Book is currently issued to a student and cannot be deleted", "danger")
        else:
            db.issued_books.delete_many({"book_id": id})
            db.books.delete_one({"id": id})
            flash("Book deleted successfully", "success")
    except Exception:
        flash("Error deleting book", "danger")

    return redirect(url_for("books"))


# Students
@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        mobile = request.form.get("mobile", "").strip()
        class_name = request.form.get("class_name", "").strip()

        if name:
            db.students.insert_one({
                "id": get_next_id(db, "students"),
                "name": name,
                "email": email,
                "mobile": mobile,
                "class_name": class_name
            })
            flash("Student added successfully", "success")
        else:
            flash("Student name is required", "danger")

        return redirect(url_for("students"))

    student_list = list(db.students.find().sort("id", -1))
    return render_template("students.html", students=student_list)


@app.route("/delete_student/<int:id>", methods=["POST"])
@login_required
def delete_student(id):
    db = get_db()

    try:
        if db.issued_books.find_one({"student_id": id, "status": "Issued"}):
            flash("Student has unreturned books and cannot be deleted", "danger")
        else:
            db.issued_books.delete_many({"student_id": id})
            db.students.delete_one({"id": id})
            flash("Student deleted successfully", "success")
    except Exception:
        flash("Error deleting student", "danger")

    return redirect(url_for("students"))


def parse_date(val):
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val)
    return None


# Issue Book (With Fine Calculation & Return History)
@app.route("/issue", methods=["GET", "POST"])
@login_required
def issue():
    db = get_db()

    if request.method == "POST":
        try:
            book_id = int(request.form["book_id"])
            student_id = int(request.form["student_id"])

            book = db.books.find_one({"id": book_id})
            student = db.students.find_one({"id": student_id})

            if not book or book.get("quantity", 0) <= 0:
                raise ValueError("Book is not available")

            if not student:
                raise ValueError("Student not found")

            if db.issued_books.find_one({
                "book_id": book_id,
                "student_id": student_id,
                "status": "Issued"
            }):
                raise ValueError("This book is already issued to this student")

            issue_date = date.today()
            due_date = issue_date + timedelta(days=14)

            db.books.update_one({"id": book_id}, {"$inc": {"quantity": -1}})

            db.issued_books.insert_one({
                "id": get_next_id(db, "issued_books"),
                "book_id": book_id,
                "student_id": student_id,
                "issue_date": issue_date.isoformat(),
                "due_date": due_date.isoformat(),
                "return_date": None,
                "status": "Issued"
            })

            flash("Book issued successfully", "success")

        except Exception as e:
            flash(str(e), "danger")

        return redirect(url_for("issue"))

    book_list = list(db.books.find({"quantity": {"$gt": 0}}))
    student_list = list(db.students.find().sort("name", 1))

    books_map = {b["id"]: b["title"] for b in db.books.find()}
    students_map = {s["id"]: s["name"] for s in db.students.find()}

    today = date.today()
    fine_per_day = 5

    raw_issued = list(db.issued_books.find({"status": "Issued"}).sort("id", -1))
    issued_list = []
    for item in raw_issued:
        due_dt = parse_date(item.get("due_date"))
        overdue_days = (today - due_dt).days if (due_dt and today > due_dt) else 0
        issued_list.append({
            "id": item["id"],
            "title": books_map.get(item["book_id"], "Unknown Book"),
            "name": students_map.get(item["student_id"], "Unknown Student"),
            "issue_date": item.get("issue_date"),
            "due_date": item.get("due_date"),
            "overdue_days": overdue_days,
            "fine": overdue_days * fine_per_day
        })

    raw_returned = list(
        db.issued_books.find({"status": "Returned"})
        .sort([("return_date", -1), ("id", -1)])
        .limit(25)
    )
    returned_list = []
    for item in raw_returned:
        due_dt = parse_date(item.get("due_date"))
        ret_dt = parse_date(item.get("return_date"))
        late_days = (ret_dt - due_dt).days if (ret_dt and due_dt and ret_dt > due_dt) else 0
        returned_list.append({
            "id": item["id"],
            "title": books_map.get(item["book_id"], "Unknown Book"),
            "name": students_map.get(item["student_id"], "Unknown Student"),
            "issue_date": item.get("issue_date"),
            "due_date": item.get("due_date"),
            "return_date": item.get("return_date"),
            "fine_paid": late_days * fine_per_day
        })

    return render_template(
        "issue.html",
        books=book_list,
        students=student_list,
        issued=issued_list,
        returned=returned_list,
        today=today
    )


# Return Book
@app.route("/return_book/<int:id>", methods=["POST"])
@login_required
def return_book(id):
    db = get_db()

    try:
        record = db.issued_books.find_one({"id": id})

        if not record or record.get("status") != "Issued":
            raise ValueError("Invalid or already returned book")

        today = date.today()
        due_dt = parse_date(record.get("due_date"))
        fine = (today - due_dt).days * 5 if (due_dt and today > due_dt) else 0

        db.issued_books.update_one(
            {"id": id},
            {"$set": {"status": "Returned", "return_date": today.isoformat()}}
        )

        db.books.update_one({"id": record["book_id"]}, {"$inc": {"quantity": 1}})

        if fine > 0:
            flash(f"Book returned successfully. Late Fine Collected: ₹{fine}", "success")
        else:
            flash("Book returned on time (No fine)", "success")

    except Exception as e:
        flash(str(e), "danger")

    return redirect(url_for("issue"))


if __name__ == "__main__":
    create_admin()
    app.run(debug=True)